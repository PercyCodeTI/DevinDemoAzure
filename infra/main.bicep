@description('Nome curto do ambiente (dev|prod).')
@allowed(['dev', 'prod'])
param ambiente string = 'dev'

@description('Prefixo dos recursos.')
param prefixo string = 'simapos'

@description('Região dos recursos.')
param location string = resourceGroup().location

@description('SKU do App Service Plan.')
param appServicePlanSku string = ambiente == 'prod' ? 'P1v3' : 'B1'

@description('Número mínimo/máximo de instâncias no autoscale (somente prod).')
param instanciasMin int = 1
param instanciasMax int = 5

@description('Cria Azure Front Door + WAF (pode ser dispensado na v1 por custo).')
param habilitarFrontDoor bool = ambiente == 'prod'

@description('E-mail para receber os alertas do Azure Monitor.')
param emailAlertas string

@description('Chave da API administrativa (GET /api/simulations).')
@secure()
param adminApiKey string

@description('Objeto (principal) ID do administrador Entra ID do SQL Server.')
param sqlAdminObjectId string

@description('Nome de login do administrador Entra ID do SQL Server.')
param sqlAdminLogin string

@description('Modelo GPT publicado no Azure AI Foundry para o chatbot.')
param modeloChat string = 'gpt-4o-mini'
param modeloChatVersao string = '2024-07-18'

@description('Capacidade do deployment do modelo, em milhares de tokens por minuto.')
param modeloChatCapacidade int = 30

@description('Acessa o Azure SQL apenas por Private Endpoint (exigido por policy que desabilita o endpoint público).')
param habilitarRedePrivada bool = true

@description('Espaço de endereçamento da VNet usada pela integração do App Service.')
param prefixoVnet string = '10.20.0.0/16'
param prefixoSubnetApp string = '10.20.1.0/24'
param prefixoSubnetPrivada string = '10.20.2.0/24'

var sufixo = '${prefixo}-${ambiente}'
var sufixoCurto = '${prefixo}${ambiente}${uniqueString(resourceGroup().id)}'
var nomeWebApp = 'app-${sufixo}-${uniqueString(resourceGroup().id)}'
var usaSlot = ambiente == 'prod'

// Identidade gerenciada usada pelo App Service para autenticar no SQL sem senha.
resource identidadeApp 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${sufixo}'
  location: location
}

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = if (habilitarRedePrivada) {
  name: 'vnet-${sufixo}'
  location: location
  properties: {
    addressSpace: { addressPrefixes: [prefixoVnet] }
    subnets: [
      {
        name: 'snet-app'
        properties: {
          addressPrefix: prefixoSubnetApp
          delegations: [
            {
              name: 'appservice'
              properties: { serviceName: 'Microsoft.Web/serverFarms' }
            }
          ]
        }
      }
      {
        name: 'snet-privado'
        properties: {
          addressPrefix: prefixoSubnetPrivada
        }
      }
    ]
  }
}

resource zonaDnsSql 'Microsoft.Network/privateDnsZones@2020-06-01' = if (habilitarRedePrivada) {
  name: 'privatelink${environment().suffixes.sqlServerHostname}'
  location: 'global'
}

resource zonaDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (habilitarRedePrivada) {
  parent: zonaDnsSql
  name: 'link-vnet'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet!.id }
  }
}

resource peSql 'Microsoft.Network/privateEndpoints@2023-11-01' = if (habilitarRedePrivada) {
  name: 'pe-sql-${sufixo}'
  location: location
  properties: {
    subnet: { id: '${vnet!.id}/subnets/snet-privado' }
    privateLinkServiceConnections: [
      {
        name: 'sql'
        properties: {
          privateLinkServiceId: sqlServer.id
          groupIds: ['sqlServer']
        }
      }
    ]
  }
}

resource peSqlDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (habilitarRedePrivada) {
  parent: peSql
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'sql'
        properties: { privateDnsZoneId: zonaDnsSql!.id }
      }
    ]
  }
}

// Azure AI Foundry: recurso de IA que hospeda o modelo GPT usado pelo chatbot.
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'aif-${sufixo}-${uniqueString(resourceGroup().id)}'
  location: location
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    // Subdomínio próprio é pré-requisito para autenticar com Entra ID em vez de chave.
    customSubDomainName: 'aif-${sufixoCurto}'
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
    allowProjectManagement: true
  }
}

resource projetoFoundry 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'proj-${sufixo}'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'Simulador de Aposentadoria'
    description: 'Recomendações financeiras sobre a simulação do usuário'
  }
}

resource deploymentChat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: modeloChat
  sku: {
    name: 'GlobalStandard'
    capacity: modeloChatCapacidade
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modeloChat
      version: modeloChatVersao
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

// Cognitive Services OpenAI User: permite ao App Service chamar o modelo sem chave de API.
resource papelFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  scope: foundry
  name: guid(foundry.id, identidadeApp.id, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalId: identidadeApp.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${sufixo}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${sufixo}'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${take(sufixoCurto, 20)}'
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'plan-${sufixo}'
  location: location
  sku: {
    name: appServicePlanSku
    capacity: 1
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

var appSettingsComuns = [
  { name: 'AMBIENTE', value: ambiente }
  { name: 'SQL_SERVER', value: '${sqlServer.name}${environment().suffixes.sqlServerHostname}' }
  { name: 'SQL_DATABASE', value: sqlDatabase.name }
  { name: 'SQL_MI_CLIENT_ID', value: identidadeApp.properties.clientId }
  { name: 'ADMIN_API_KEY', value: adminApiKey }
  { name: 'RETENCAO_MESES', value: '24' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
  // 'disabled': a telemetria vem do SDK azure-monitor-opentelemetry na aplicação.
  { name: 'ApplicationInsightsAgent_EXTENSION_VERSION', value: 'disabled' }
  { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
  { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: '600' }
  { name: 'KEY_VAULT_URI', value: keyVault.properties.vaultUri }
  { name: 'AZURE_AI_ENDPOINT', value: foundry.properties.endpoint }
  { name: 'AZURE_AI_DEPLOYMENT', value: deploymentChat.name }
]

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: nomeWebApp
  location: location
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${identidadeApp.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: habilitarRedePrivada ? '${vnet!.id}/subnets/snet-app' : null
    vnetRouteAllEnabled: habilitarRedePrivada
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      alwaysOn: appServicePlanSku != 'B1' ? true : false
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      healthCheckPath: '/health'
      appCommandLine: 'bash startup.sh'
      appSettings: appSettingsComuns
    }
  }
}

resource slotStaging 'Microsoft.Web/sites/slots@2023-12-01' = if (usaSlot) {
  parent: webApp
  name: 'staging'
  location: location
  identity: {
    type: 'SystemAssigned, UserAssigned'
    userAssignedIdentities: {
      '${identidadeApp.id}': {}
    }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: habilitarRedePrivada ? '${vnet!.id}/subnets/snet-app' : null
    vnetRouteAllEnabled: habilitarRedePrivada
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      healthCheckPath: '/health'
      appCommandLine: 'bash startup.sh'
      appSettings: appSettingsComuns
    }
  }
}

resource autoscale 'Microsoft.Insights/autoscalesettings@2022-10-01' = if (usaSlot) {
  name: 'autoscale-${sufixo}'
  location: location
  properties: {
    enabled: true
    targetResourceUri: plan.id
    profiles: [
      {
        name: 'cpu'
        capacity: {
          minimum: string(instanciasMin)
          maximum: string(instanciasMax)
          default: string(instanciasMin)
        }
        rules: [
          {
            metricTrigger: {
              metricName: 'CpuPercentage'
              metricResourceUri: plan.id
              timeGrain: 'PT1M'
              statistic: 'Average'
              timeWindow: 'PT5M'
              timeAggregation: 'Average'
              operator: 'GreaterThan'
              threshold: 70
            }
            scaleAction: {
              direction: 'Increase'
              type: 'ChangeCount'
              value: '1'
              cooldown: 'PT5M'
            }
          }
          {
            metricTrigger: {
              metricName: 'CpuPercentage'
              metricResourceUri: plan.id
              timeGrain: 'PT1M'
              statistic: 'Average'
              timeWindow: 'PT10M'
              timeAggregation: 'Average'
              operator: 'LessThan'
              threshold: 40
            }
            scaleAction: {
              direction: 'Decrease'
              type: 'ChangeCount'
              value: '1'
              cooldown: 'PT10M'
            }
          }
        ]
      }
    ]
  }
}

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: 'sql-${sufixo}-${uniqueString(resourceGroup().id)}'
  location: location
  properties: {
    minimalTlsVersion: '1.2'
    publicNetworkAccess: habilitarRedePrivada ? 'Disabled' : 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      login: habilitarRedePrivada ? identidadeApp.name : sqlAdminLogin
      sid: habilitarRedePrivada ? identidadeApp.properties.principalId : sqlAdminObjectId
      tenantId: subscription().tenantId
      principalType: 'Application'
      azureADOnlyAuthentication: true
    }
  }
}

resource sqlFirewallAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = if (!habilitarRedePrivada) {
  parent: sqlServer
  name: 'AllowAllWindowsAzureIps'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

resource sqlDatabase 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: 'sqldb-simulacoes'
  location: location
  sku: {
    name: 'GP_S_Gen5'
    tier: 'GeneralPurpose'
    family: 'Gen5'
    capacity: 2
  }
  properties: {
    autoPauseDelay: ambiente == 'prod' ? -1 : 60
    minCapacity: json('0.5')
    maxSizeBytes: 34359738368
    zoneRedundant: false
  }
}

resource sqlBackupShortTerm 'Microsoft.Sql/servers/databases/backupShortTermRetentionPolicies@2023-08-01-preview' = {
  parent: sqlDatabase
  name: 'default'
  properties: {
    retentionDays: 7
  }
}

resource diagSql 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: sqlDatabase
  name: 'diag-sql'
  properties: {
    workspaceId: logAnalytics.id
    metrics: [
      { category: 'Basic', enabled: true }
      { category: 'InstanceAndAppAdvanced', enabled: true }
    ]
    logs: [
      { categoryGroup: 'allLogs', enabled: true }
    ]
  }
}

resource diagWebApp 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: webApp
  name: 'diag-app'
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      { category: 'AppServiceHTTPLogs', enabled: true }
      { category: 'AppServiceConsoleLogs', enabled: true }
      { category: 'AppServiceAppLogs', enabled: true }
      { category: 'AppServicePlatformLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

module frontDoor 'frontdoor.bicep' = if (habilitarFrontDoor) {
  name: 'frontdoor'
  params: {
    nome: 'afd-${sufixo}'
    origemHost: webApp.properties.defaultHostName
  }
}

module monitoramento 'monitoring.bicep' = {
  name: 'monitoramento'
  params: {
    sufixo: sufixo
    location: location
    emailAlertas: emailAlertas
    appInsightsId: appInsights.id
    webAppId: webApp.id
    planId: plan.id
    sqlDatabaseId: sqlDatabase.id
    urlHealth: 'https://${webApp.properties.defaultHostName}/health'
  }
}

output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName string = sqlDatabase.name
output webAppPrincipalId string = webApp.identity.principalId
output identidadeAppClientId string = identidadeApp.properties.clientId
output redePrivada bool = habilitarRedePrivada
output frontDoorUrl string = habilitarFrontDoor ? frontDoor!.outputs.endpointHostName : ''
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output foundryEndpoint string = foundry.properties.endpoint
output foundryDeployment string = deploymentChat.name
output foundryProject string = projetoFoundry.name

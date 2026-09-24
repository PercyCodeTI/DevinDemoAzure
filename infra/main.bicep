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

var sufixo = '${prefixo}-${ambiente}'
var sufixoCurto = '${prefixo}${ambiente}${uniqueString(resourceGroup().id)}'
var nomeWebApp = 'app-${sufixo}-${uniqueString(resourceGroup().id)}'
var usaSlot = ambiente == 'prod'

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
  { name: 'ADMIN_API_KEY', value: adminApiKey }
  { name: 'RETENCAO_MESES', value: '24' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
  { name: 'ApplicationInsightsAgent_EXTENSION_VERSION', value: '~3' }
  { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
  { name: 'WEBSITES_CONTAINER_START_TIME_LIMIT', value: '600' }
  { name: 'KEY_VAULT_URI', value: keyVault.properties.vaultUri }
]

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: nomeWebApp
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
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
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
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
    publicNetworkAccess: 'Enabled'
    administrators: {
      administratorType: 'ActiveDirectory'
      login: sqlAdminLogin
      sid: sqlAdminObjectId
      tenantId: subscription().tenantId
      principalType: 'Application'
      azureADOnlyAuthentication: true
    }
  }
}

resource sqlFirewallAzure 'Microsoft.Sql/servers/firewallRules@2023-08-01-preview' = {
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
output frontDoorUrl string = habilitarFrontDoor ? frontDoor!.outputs.endpointHostName : ''
output appInsightsConnectionString string = appInsights.properties.ConnectionString

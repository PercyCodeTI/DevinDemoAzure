@description('Sufixo de nomes.')
param sufixo string
param location string
param emailAlertas string
param appInsightsId string
param webAppId string
param planId string
param sqlDatabaseId string
param urlHealth string

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = {
  name: 'ag-${sufixo}'
  location: 'global'
  properties: {
    groupShortName: 'simapos'
    enabled: true
    emailReceivers: [
      {
        name: 'time'
        emailAddress: emailAlertas
        useCommonAlertSchema: true
      }
    ]
  }
}

resource availabilityTest 'Microsoft.Insights/webtests@2022-06-15' = {
  name: 'wt-health-${sufixo}'
  location: location
  tags: {
    'hidden-link:${appInsightsId}': 'Resource'
  }
  properties: {
    Name: 'wt-health-${sufixo}'
    SyntheticMonitorId: 'wt-health-${sufixo}'
    Enabled: true
    Frequency: 300
    Timeout: 30
    Kind: 'standard'
    RetryEnabled: true
    Locations: [
      { Id: 'us-il-ch1-azr' }
      { Id: 'us-ca-sjc-azr' }
      { Id: 'us-va-ash-azr' }
    ]
    Request: {
      RequestUrl: urlHealth
      HttpVerb: 'GET'
      ParseDependentRequests: false
    }
    ValidationRules: {
      ExpectedHttpStatusCode: 200
      SSLCheck: true
      SSLCertRemainingLifetimeCheck: 7
    }
  }
}

resource alertaLatencia 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alerta-latencia-${sufixo}'
  location: 'global'
  properties: {
    description: 'p95 de latência do App Service acima de 1s por 5 min'
    severity: 2
    enabled: true
    scopes: [webAppId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'latencia'
          metricName: 'HttpResponseTime'
          metricNamespace: 'Microsoft.Web/sites'
          operator: 'GreaterThan'
          threshold: 1
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

resource alertaErros5xx 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alerta-5xx-${sufixo}'
  location: 'global'
  properties: {
    description: 'Erros 5xx acima do limite por 5 min'
    severity: 1
    enabled: true
    scopes: [webAppId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'http5xx'
          metricName: 'Http5xx'
          metricNamespace: 'Microsoft.Web/sites'
          operator: 'GreaterThan'
          threshold: 5
          timeAggregation: 'Total'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

resource alertaCpu 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alerta-cpu-${sufixo}'
  location: 'global'
  properties: {
    description: 'CPU média do plano acima de 85% por 10 min'
    severity: 3
    enabled: true
    scopes: [planId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT10M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'cpu'
          metricName: 'CpuPercentage'
          metricNamespace: 'Microsoft.Web/serverfarms'
          operator: 'GreaterThan'
          threshold: 85
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

resource alertaSqlCpu 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alerta-sql-cpu-${sufixo}'
  location: 'global'
  properties: {
    description: 'Uso de vCore do Azure SQL acima de 85% por 10 min'
    severity: 2
    enabled: true
    scopes: [sqlDatabaseId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT10M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'sqlcpu'
          metricName: 'cpu_percent'
          metricNamespace: 'Microsoft.Sql/servers/databases'
          operator: 'GreaterThan'
          threshold: 85
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

resource alertaSqlEspaco 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alerta-sql-espaco-${sufixo}'
  location: 'global'
  properties: {
    description: 'Espaço do banco acima de 80% da capacidade alocada'
    severity: 3
    enabled: true
    scopes: [sqlDatabaseId]
    evaluationFrequency: 'PT15M'
    windowSize: 'PT1H'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'espaco'
          metricName: 'storage_percent'
          metricNamespace: 'Microsoft.Sql/servers/databases'
          operator: 'GreaterThan'
          threshold: 80
          timeAggregation: 'Average'
          criterionType: 'StaticThresholdCriterion'
        }
      ]
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

resource alertaFalhaGravacao 'Microsoft.Insights/scheduledQueryRules@2023-03-15-preview' = {
  name: 'alerta-falha-gravacao-${sufixo}'
  location: location
  properties: {
    description: 'Falhas de gravação de simulações no banco'
    severity: 1
    enabled: true
    scopes: [appInsightsId]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      allOf: [
        {
          query: 'traces | union exceptions | where message has "falha_gravacao_simulacao" or outerMessage has "falha_gravacao_simulacao" | summarize Total = count()'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    actions: {
      actionGroups: [actionGroup.id]
    }
  }
}

resource alertaDisponibilidade 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'alerta-disponibilidade-${sufixo}'
  location: 'global'
  properties: {
    description: 'Availability test de /health falhando em 2 ou mais regiões'
    severity: 1
    enabled: true
    scopes: [availabilityTest.id, appInsightsId]
    evaluationFrequency: 'PT1M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria'
      webTestId: availabilityTest.id
      componentId: appInsightsId
      failedLocationCount: 2
    }
    actions: [{ actionGroupId: actionGroup.id }]
  }
}

output actionGroupId string = actionGroup.id

using './main.bicep'

param ambiente = 'prod'
param appServicePlanSku = 'P1v3'
param habilitarFrontDoor = true
param instanciasMin = 1
param instanciasMax = 5
param emailAlertas = 'percy.machado.ti@gmail.com'
param adminApiKey = readEnvironmentVariable('ADMIN_API_KEY', '')
param sqlAdminObjectId = readEnvironmentVariable('SQL_ADMIN_OBJECT_ID', '')
param sqlAdminLogin = readEnvironmentVariable('SQL_ADMIN_LOGIN', 'devin-deployer')

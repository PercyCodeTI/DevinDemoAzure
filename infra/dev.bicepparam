using './main.bicep'

param ambiente = 'dev'
param appServicePlanSku = 'B1'
param habilitarFrontDoor = false
param emailAlertas = 'percy.machado.ti@gmail.com'
param adminApiKey = readEnvironmentVariable('ADMIN_API_KEY', '')
param sqlAdminObjectId = readEnvironmentVariable('SQL_ADMIN_OBJECT_ID', '')
param sqlAdminLogin = readEnvironmentVariable('SQL_ADMIN_LOGIN', 'devin-deployer')

-- Concede acesso ao banco para a Managed Identity do App Service.
-- Substitua {{APP_NAME}} pelo nome do Web App (ou do slot) antes de executar.
-- Executar conectado ao banco `sqldb-simulacoes` com o administrador Entra ID.
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = '{{APP_NAME}}')
BEGIN
    CREATE USER [{{APP_NAME}}] FROM EXTERNAL PROVIDER;
END
ALTER ROLE db_datareader ADD MEMBER [{{APP_NAME}}];
ALTER ROLE db_datawriter ADD MEMBER [{{APP_NAME}}];
ALTER ROLE db_ddladmin ADD MEMBER [{{APP_NAME}}];

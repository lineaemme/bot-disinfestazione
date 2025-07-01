# Bot Disinfestazione

Bot Telegram per la raccolta rapporti di interventi di disinfestazione.

## Funzionalità
- Questionario guidato per raccolta dati intervento
- Upload foto quietanza
- Salvataggio automatico su Google Sheets
- Archiviazione foto su Google Drive

## Setup
1. Crea bot Telegram con @BotFather
2. Configura Google APIs (Sheets + Drive)
3. Configura variabili ambiente su Render
4. Deploy automatico

## Variabili Ambiente Necessarie
- `TELEGRAM_TOKEN`: Token del bot Telegram
- `GOOGLE_SPREADSHEET_ID`: ID del foglio Google Sheets
- `GOOGLE_DRIVE_FOLDER_ID`: ID cartella Google Drive
- `GOOGLE_CREDENTIALS_JSON`: Credenziali service account Google

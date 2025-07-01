import logging
import os
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import json

# Stati del conversationHandler
NOME, CLIENTE, INDIRIZZO, TIPO_INTERVENTO, PRODOTTI, NOTE, FOTO = range(7)

# Configurazione
TOKEN = os.getenv('TELEGRAM_TOKEN')
SPREADSHEET_ID = os.getenv('GOOGLE_SPREADSHEET_ID')
DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')

# Setup Google APIs
def setup_google_services():
    """Configura i servizi Google Sheets e Drive"""
    # Le credenziali JSON dovranno essere nelle variabili ambiente
    creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
    if creds_json:
        creds_dict = json.loads(creds_json)
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=[
                'https://www.googleapis.com/auth/spreadsheets',
                'https://www.googleapis.com/auth/drive.file'
            ]
        )
        
        # Google Sheets
        gc = gspread.authorize(credentials)
        
        # Google Drive
        drive_service = build('drive', 'v3', credentials=credentials)
        
        return gc, drive_service
    return None, None

# Inizializza servizi Google
gc, drive_service = setup_google_services()

# Dizionario per memorizzare i dati della sessione utente
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inizia la conversazione"""
    user_id = update.effective_user.id
    user_data[user_id] = {}
    
    await update.message.reply_text(
        "🦟 Bot Disinfestazione - Rapporto Intervento\n\n"
        "Compila il questionario per registrare l'intervento.\n\n"
        "Iniziamo! Qual è il tuo nome?"
    )
    
    return NOME

async def get_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie il nome dell'operatore"""
    user_id = update.effective_user.id
    user_data[user_id]['nome'] = update.message.text
    
    await update.message.reply_text(
        f"Ciao {update.message.text}! 👋\n\n"
        "Qual è il nome del cliente?"
    )
    
    return CLIENTE

async def get_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie il nome del cliente"""
    user_id = update.effective_user.id
    user_data[user_id]['cliente'] = update.message.text
    
    await update.message.reply_text(
        "Perfetto! Ora inserisci l'indirizzo completo dell'intervento:"
    )
    
    return INDIRIZZO

async def get_indirizzo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie l'indirizzo dell'intervento"""
    user_id = update.effective_user.id
    user_data[user_id]['indirizzo'] = update.message.text
    
    # Tastiera con opzioni tipo intervento
    keyboard = [
        ['🪳 Blatte', '🐜 Formiche'],
        ['🦟 Zanzare', '🐭 Roditori'],
        ['🕷️ Ragni', '🦂 Altri insetti'],
        ['🌿 Diserbante', '💨 Sanificazione']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    
    await update.message.reply_text(
        "Che tipo di disinfestazione hai effettuato?",
        reply_markup=reply_markup
    )
    
    return TIPO_INTERVENTO

async def get_tipo_intervento(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie il tipo di intervento"""
    user_id = update.effective_user.id
    user_data[user_id]['tipo_intervento'] = update.message.text
    
    await update.message.reply_text(
        "Quali prodotti hai utilizzato? (elenca i nomi dei prodotti)",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return PRODOTTI

async def get_prodotti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie i prodotti utilizzati"""
    user_id = update.effective_user.id
    user_data[user_id]['prodotti'] = update.message.text
    
    await update.message.reply_text(
        "Hai delle note aggiuntive sull'intervento?\n"
        "(Scrivi 'nessuna' se non hai note)"
    )
    
    return NOTE

async def get_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie le note"""
    user_id = update.effective_user.id
    user_data[user_id]['note'] = update.message.text
    
    await update.message.reply_text(
        "📸 Perfetto! Ora invia una foto della quietanza/ricevuta.\n\n"
        "Assicurati che la foto sia leggibile!"
    )
    
    return FOTO

async def get_foto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie la foto e salva tutto"""
    user_id = update.effective_user.id
    
    if not update.message.photo:
        await update.message.reply_text(
            "Per favore invia una foto della quietanza."
        )
        return FOTO
    
    try:
        await update.message.reply_text("📝 Sto salvando i dati...")
        
        # Scarica la foto
        photo_file = await update.message.photo[-1].get_file()
        photo_data = await photo_file.download_as_bytearray()
        
        # Nome file con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"quietanza_{user_data[user_id]['cliente']}_{timestamp}.jpg"
        
        # Upload su Google Drive
        photo_url = ""
        if drive_service:
            media = MediaIoBaseUpload(
                io.BytesIO(photo_data),
                mimetype='image/jpeg',
                resumable=True
            )
            
            file_metadata = {
                'name': filename,
                'parents': [DRIVE_FOLDER_ID] if DRIVE_FOLDER_ID else []
            }
            
            file = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,webViewLink'
            ).execute()
            
            photo_url = file.get('webViewLink', '')
        
        # Prepara i dati per Google Sheets
        now = datetime.now()
        row_data = [
            now.strftime("%d/%m/%Y"),
            now.strftime("%H:%M"),
            user_data[user_id]['nome'],
            user_data[user_id]['cliente'],
            user_data[user_id]['indirizzo'],
            user_data[user_id]['tipo_intervento'],
            user_data[user_id]['prodotti'],
            user_data[user_id]['note'],
            photo_url,
            "Completato"
        ]
        
        # Salva su Google Sheets
        if gc and SPREADSHEET_ID:
            sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
            sheet.append_row(row_data)
        
        # Messaggio di conferma
        riepilogo = f"""
✅ **Intervento registrato con successo!**

📋 **Riepilogo:**
👤 **Operatore:** {user_data[user_id]['nome']}
🏢 **Cliente:** {user_data[user_id]['cliente']}
📍 **Indirizzo:** {user_data[user_id]['indirizzo']}
🦟 **Tipo:** {user_data[user_id]['tipo_intervento']}
🧪 **Prodotti:** {user_data[user_id]['prodotti']}
📝 **Note:** {user_data[user_id]['note']}
📸 **Foto:** Caricata
⏰ **Data/Ora:** {now.strftime("%d/%m/%Y alle %H:%M")}

I dati sono stati salvati nel sistema aziendale.
        """
        
        await update.message.reply_text(riepilogo, parse_mode='Markdown')
        
        # Pulisci i dati utente
        del user_data[user_id]
        
        return ConversationHandler.END
        
    except Exception as e:
        logging.error(f"Errore nel salvare i dati: {e}")
        await update.message.reply_text(
            "❌ Si è verificato un errore nel salvare i dati. "
            "Riprova o contatta l'assistenza."
        )
        return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancella la conversazione"""
    user_id = update.effective_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    await update.message.reply_text(
        "Operazione annullata. Usa /start per iniziare un nuovo rapporto.",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return ConversationHandler.END

def main():
    """Avvia il bot"""
    if not TOKEN:
        print("❌ TELEGRAM_TOKEN non configurato!")
        return
    
    # Crea l'applicazione
    application = Application.builder().token(TOKEN).build()
    
    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_nome)],
            CLIENTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cliente)],
            INDIRIZZO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_indirizzo)],
            TIPO_INTERVENTO: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tipo_intervento)],
            PRODOTTI: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_prodotti)],
            NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_note)],
            FOTO: [MessageHandler(filters.PHOTO, get_foto)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    application.add_handler(conv_handler)
    
    # Avvia il bot
    print("🤖 Bot avviato! Premi Ctrl+C per fermare.")
    application.run_polling()

if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    main()

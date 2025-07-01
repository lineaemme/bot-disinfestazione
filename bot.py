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
import asyncio
from aiohttp import web
import threading

# Setup logging semplificato
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Stati del conversationHandler
NOME, CLIENTE, INDIRIZZO, TIPO_INTERVENTO, PRODOTTI, NOTE, FOTO = range(7)

# Configurazione
TOKEN = os.getenv('TELEGRAM_TOKEN')
SPREADSHEET_ID = os.getenv('GOOGLE_SPREADSHEET_ID')
DRIVE_FOLDER_ID = os.getenv('GOOGLE_DRIVE_FOLDER_ID')
PORT = int(os.getenv('PORT', 10000))

print(f"🔧 Configurazione:")
print(f"- TOKEN presente: {'✅' if TOKEN else '❌'}")
print(f"- SPREADSHEET_ID presente: {'✅' if SPREADSHEET_ID else '❌'}")
print(f"- DRIVE_FOLDER_ID presente: {'✅' if DRIVE_FOLDER_ID else '❌'}")
print(f"- CREDENTIALS presente: {'✅' if os.getenv('GOOGLE_CREDENTIALS_JSON') else '❌'}")
print(f"- PORT: {PORT}")

# Setup Google APIs
def setup_google_services():
    """Configura i servizi Google Sheets e Drive"""
    try:
        creds_json = os.getenv('GOOGLE_CREDENTIALS_JSON')
        if not creds_json:
            print("⚠️ GOOGLE_CREDENTIALS_JSON non configurato")
            return None, None
            
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
        
        print("✅ Google APIs configurate")
        return gc, drive_service
        
    except Exception as e:
        print(f"❌ Errore Google APIs: {e}")
        return None, None

# Inizializza servizi Google
gc, drive_service = setup_google_services()

# Dizionario per memorizzare i dati della sessione utente
user_data = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Inizia la conversazione"""
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or "Utente"
    
    print(f"🆕 Nuovo utente: {first_name} - ID: {user_id}")
    
    user_data[user_id] = {}
    
    await update.message.reply_text(
        f"🦟 Bot Disinfestazione - Rapporto Intervento\n\n"
        f"Benvenuto {first_name}! 👋\n\n"
        "Compila il questionario per registrare l'intervento.\n\n"
        "Iniziamo! Qual è il tuo nome completo?"
    )
    
    return NOME

async def get_nome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie il nome dell'operatore"""
    user_id = update.effective_user.id
    user_data[user_id]['nome'] = update.message.text.strip()
    
    await update.message.reply_text(
        f"Ciao {update.message.text}! 👋\n\n"
        "Qual è il nome del cliente?"
    )
    
    return CLIENTE

async def get_cliente(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie il nome del cliente"""
    user_id = update.effective_user.id
    user_data[user_id]['cliente'] = update.message.text.strip()
    
    await update.message.reply_text(
        "Perfetto! Ora inserisci l'indirizzo completo dell'intervento:"
    )
    
    return INDIRIZZO

async def get_indirizzo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie l'indirizzo dell'intervento"""
    user_id = update.effective_user.id
    user_data[user_id]['indirizzo'] = update.message.text.strip()
    
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
    user_data[user_id]['tipo_intervento'] = update.message.text.strip()
    
    await update.message.reply_text(
        "Quali prodotti hai utilizzato? (elenca i nomi dei prodotti)",
        reply_markup=ReplyKeyboardRemove()
    )
    
    return PRODOTTI

async def get_prodotti(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie i prodotti utilizzati"""
    user_id = update.effective_user.id
    user_data[user_id]['prodotti'] = update.message.text.strip()
    
    await update.message.reply_text(
        "Hai delle note aggiuntive sull'intervento?\n"
        "(Scrivi 'nessuna' se non hai note)"
    )
    
    return NOTE

async def get_note(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Raccoglie le note"""
    user_id = update.effective_user.id
    user_data[user_id]['note'] = update.message.text.strip()
    
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
        print(f"💾 Salvando dati per utente {user_id}")
        
        # Scarica la foto
        photo_file = await update.message.photo[-1].get_file()
        photo_data = await photo_file.download_as_bytearray()
        
        # Nome file con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cliente_safe = "".join(c for c in user_data[user_id]['cliente'] if c.isalnum() or c in (' ', '-', '_')).rstrip()
        cliente_safe = cliente_safe.replace(' ', '_')
        filename = f"quietanza_{cliente_safe}_{timestamp}.jpg"
        
        # Upload su Google Drive
        photo_url = "Foto caricata"
        if drive_service and DRIVE_FOLDER_ID:
            try:
                media = MediaIoBaseUpload(
                    io.BytesIO(photo_data),
                    mimetype='image/jpeg',
                    resumable=True
                )
                
                file_metadata = {
                    'name': filename,
                    'parents': [DRIVE_FOLDER_ID]
                }
                
                file = drive_service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id,webViewLink'
                ).execute()
                
                photo_url = file.get('webViewLink', 'Link non disponibile')
                print(f"📸 Foto caricata: {filename}")
                
            except Exception as e:
                print(f"❌ Errore upload Drive: {e}")
                photo_url = "Errore caricamento foto"
        else:
            print("⚠️ Drive non configurato")
        
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
            try:
                sheet = gc.open_by_key(SPREADSHEET_ID).sheet1
                sheet.append_row(row_data)
                print(f"📊 Dati salvati su Sheets")
            except Exception as e:
                print(f"❌ Errore Sheets: {e}")
        else:
            print("⚠️ Sheets non configurato")
        
        # Messaggio di conferma
        riepilogo = f"""✅ **Intervento registrato con successo!**

📋 **Riepilogo:**
👤 **Operatore:** {user_data[user_id]['nome']}
🏢 **Cliente:** {user_data[user_id]['cliente']}
📍 **Indirizzo:** {user_data[user_id]['indirizzo']}
🦟 **Tipo:** {user_data[user_id]['tipo_intervento']}
🧪 **Prodotti:** {user_data[user_id]['prodotti']}
📝 **Note:** {user_data[user_id]['note']}
📸 **Foto:** Caricata
⏰ **Data/Ora:** {now.strftime("%d/%m/%Y alle %H:%M")}

I dati sono stati salvati nel sistema aziendale."""
        
        await update.message.reply_text(riepilogo, parse_mode='Markdown')
        
        # Pulisci i dati utente
        del user_data[user_id]
        print(f"✅ Intervento completato per utente {user_id}")
        
        return ConversationHandler.END
        
    except Exception as e:
        print(f"❌ Errore nel salvare: {e}")
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

# Server web per soddisfare Render
async def health_check(request):
    return web.Response(text="Bot funzionante!")

async def start_web_server():
    """Avvia il server web per Render"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    print(f"🌐 Server web avviato sulla porta {PORT}")

def main():
    """Avvia il bot"""
    if not TOKEN:
        print("❌ TELEGRAM_TOKEN non configurato!")
        return
    
    try:
        print("🚀 Inizializzazione bot...")
        
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
        
        print("🤖 Bot configurato!")
        print("📊 Configurazione:")
        print(f"  - Google Sheets: {'✅' if gc else '❌'}")
        print(f"  - Google Drive: {'✅' if drive_service else '❌'}")
        
        # Avvia il server web in background
        async def run_all():
            await start_web_server()
            await application.run_polling()
        
        # Esegui tutto insieme
        asyncio.run(run_all())
        
    except Exception as e:
        print(f"❌ Errore critico: {e}")
        logging.error(f"Errore: {e}")

if __name__ == '__main__':
    main()

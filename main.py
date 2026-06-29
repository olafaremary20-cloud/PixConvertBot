import os
import logging
from io import BytesIO
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# ============================================
# CONFIGURATION
# ============================================

TOKEN = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable not set!")

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Supported formats
SUPPORTED_FORMATS = {
    "jpg": "JPEG",
    "jpeg": "JPEG", 
    "png": "PNG",
    "webp": "WEBP",
    "gif": "GIF",
    "bmp": "BMP",
    "tiff": "TIFF",
    "ico": "ICO"
}

# ============================================
# HELPER FUNCTIONS
# ============================================

def get_format_keyboard():
    """Generate inline keyboard with format options"""
    buttons = []
    row = []
    for i, fmt in enumerate(SUPPORTED_FORMATS.keys()):
        row.append(InlineKeyboardButton(fmt.upper(), callback_data=f"convert_{fmt}"))
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(buttons)

def convert_image(image_bytes: bytes, target_format: str) -> BytesIO:
    """Convert image to target format"""
    try:
        # Open image
        img = Image.open(BytesIO(image_bytes))
        
        # Handle RGBA to RGB conversion for JPEG
        if target_format.lower() in ["jpg", "jpeg"] and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        
        # Save to bytes
        output = BytesIO()
        img.save(output, format=SUPPORTED_FORMATS[target_format.lower()])
        output.seek(0)
        return output
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        raise e

# ============================================
# BOT COMMAND HANDLERS
# ============================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message when /start is issued"""
    welcome_text = (
        "🎨 Welcome to PixConvertBot!\n\n"
        "I can convert images between different formats.\n\n"
        "📤 **How to use:**\n"
        "1. Send me an image\n"
        "2. Choose the format you want\n"
        "3. I'll convert and send it back\n\n"
        "📁 **Supported formats:**\n"
        f"{', '.join(SUPPORTED_FORMATS.keys()).upper()}\n\n"
        "Send an image to get started!"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message"""
    help_text = (
        "🆘 **PixConvertBot Help**\n\n"
        "**Commands:**\n"
        "/start - Start the bot\n"
        "/help - Show this help\n"
        "/formats - Show supported formats\n\n"
        "**How it works:**\n"
        "1. Send any image (photo or file)\n"
        "2. Click the format button\n"
        "3. Wait for conversion\n"
        "4. Download your converted image!"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def formats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show supported formats"""
    formats_text = "📁 **Supported Formats:**\n\n"
    for fmt in SUPPORTED_FORMATS.keys():
        formats_text += f"✅ {fmt.upper()}\n"
    await update.message.reply_text(formats_text, parse_mode="Markdown")

# ============================================
# IMAGE HANDLER
# ============================================

async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming images"""
    try:
        # Get image file
        if update.message.photo:
            # Photo sent as photo
            photo = update.message.photo[-1]
            file = await photo.get_file()
        elif update.message.document:
            # File sent as document
            doc = update.message.document
            if doc.mime_type and doc.mime_type.startswith("image/"):
                file = await doc.get_file()
            else:
                await update.message.reply_text("❌ Please send an image file!")
                return
        else:
            await update.message.reply_text("❌ Please send an image file!")
            return

        # Download image
        image_bytes = await file.download_as_bytearray()
        
        # Store in context for later conversion
        context.user_data["original_image"] = image_bytes
        context.user_data["original_format"] = file.file_path.split(".")[-1].lower()
        
        # Show format selection
        await update.message.reply_text(
            f"✅ Image received! Original format: {context.user_data['original_format'].upper()}\n\n"
            "🔽 Choose the format you want to convert to:",
            reply_markup=get_format_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Image handler error: {e}")
        await update.message.reply_text("❌ Failed to process image. Please try again.")

# ============================================
# CALLBACK QUERY HANDLER
# ============================================

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "cancel":
        await query.edit_message_text("❌ Conversion cancelled.")
        context.user_data.pop("original_image", None)
        return
    
    if data.startswith("convert_"):
        target_format = data.replace("convert_", "")
        
        # Check if image exists
        if "original_image" not in context.user_data:
            await query.edit_message_text(
                "❌ No image found! Please send an image first."
            )
            return
        
        try:
            # Send processing message
            await query.edit_message_text(
                f"🔄 Converting to {target_format.upper()}... Please wait."
            )
            
            # Convert image
            original_bytes = context.user_data["original_image"]
            converted = convert_image(original_bytes, target_format)
            
            # Get original format
            original_format = context.user_data.get("original_format", "image")
            
            # Send converted image
            await query.message.reply_document(
                document=converted,
                filename=f"converted.{target_format}",
                caption=f"✅ Converted from {original_format.upper()} to {target_format.upper()}"
            )
            
            # Delete processing message
            await query.message.delete()
            
            # Clean up
            context.user_data.pop("original_image", None)
            
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            await query.edit_message_text(
                f"❌ Failed to convert to {target_format.upper()}. "
                "Please try again with a different format."
            )

# ============================================
# ERROR HANDLER
# ============================================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")

# ============================================
# MAIN APPLICATION
# ============================================

def main() -> None:
    """Start the bot"""
    # Create application
    application = Application.builder().token(TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("formats", formats_command))
    
    # Add message handler for images
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.IMAGE, 
        handle_image
    ))
    
    # Add callback query handler for buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)

    # Start the bot
    logger.info("Starting PixConvertBot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

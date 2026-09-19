"""
Botni yig'ish va ishga tushirish - yagona joy. Barcha handler funksiyalari
va suhbat holatlari boshqa bot/ modullaridan import qilinadi (wildcard
import - bu yerda ataylab, chunki bu fayl ~100+ funksiyani ro'yxatga olishi
kerak va ularning HAMMASINI qo'lda sanab chiqish xato qilish ehtimolini
oshiradi; har bir modul o'zining nomlarini eksport qiladi).
"""
import asyncio
import difflib
import html
import io
import json
import logging
import re
import urllib.parse
from datetime import datetime, timedelta
from datetime import time as dtime

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    KeyboardButton,
    MessageOriginHiddenUser,
    MessageOriginUser,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, NetworkError, TimedOut
from telegram.ext import ContextTypes, ConversationHandler, filters

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PicklePersistence,
)

from common.config import ADMIN_IDS, ADMIN_USERNAME, BOT_TOKEN as TOKEN, CARD_HOLDER, CHANNEL_ID, CHANNEL_USERNAME, DASHBOARD_URL, DB_PATH, DEFAULT_SETTINGS as INITIAL_SETTINGS, MAX_DAILY_LISTINGS, MOD_DAILY_LISTINGS, STALE_CHECK_DAYS
from common.districts import seed_district_aliases

from bot.constants import *  # noqa: F401,F403
from bot.db import *  # noqa: F401,F403
from bot.helpers import *  # noqa: F401,F403
from bot.fraud_detection import *  # noqa: F401,F403
from bot.menu import *  # noqa: F401,F403
from bot.location_alerts import *  # noqa: F401,F403
from bot.admin_panel import *  # noqa: F401,F403
from bot.flow_quick import *  # noqa: F401,F403
from bot.admin_moderators import *  # noqa: F401,F403
from bot.flow_listing import *  # noqa: F401,F403
from bot.flow_subscription import *  # noqa: F401,F403
from bot.admin_moderation import *  # noqa: F401,F403
from bot.flow_complaint import *  # noqa: F401,F403
from bot.flow_edit import *  # noqa: F401,F403
from bot.flow_viewing import *  # noqa: F401,F403
from bot.jobs import *  # noqa: F401,F403
from bot.ai_concierge import *  # noqa: F401,F403

logger = logging.getLogger(__name__)

# ============================= XATOLIKLAR =============================

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Xatolik yuz berdi", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("\u26a0\ufe0f Kutilmagan xatolik yuz berdi. Iltimos, \u00abBekor qilish\u00bb tugmasini bosib qaytadan urinib ko'ring.")
        except Exception:
            pass


# ============================= ILOVANI ISHGA TUSHIRISH =============================

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN topilmadi. .env faylida BOT_TOKEN o'rnating.")
    if CHANNEL_ID is None:
        raise RuntimeError("CHANNEL_ID topilmadi. .env faylida CHANNEL_ID o'rnating.")

    init_db()
    seed_district_aliases()
    persistence = PicklePersistence(filepath="bot_persistence.pkl")
    app = (
        Application.builder().token(TOKEN).persistence(persistence)
        .connect_timeout(20).read_timeout(20).write_timeout(20).pool_timeout(20)
        .build()
    )

    nav_cb = CallbackQueryHandler(nav_router, pattern="^(nav_back|nav_cancel)$")
    text_cb = MessageHandler(filters.TEXT & ~filters.COMMAND, text_step_router)

    def make_reminder(state):
        async def _h(update, context):
            return await remind_text(update, context, state)
        return _h

    def text_state(state):
        return [nav_cb, text_cb, MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(state))]

    elon_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(BTN_ELON)}$"), elon_entry),
            CommandHandler("start", elon_entry, filters=filters.Regex(r"^/start elon$")),
            CallbackQueryHandler(listing_type_chosen, pattern="^listingtype_(free|paid)$"),
        ],
        states={
            LISTING_TYPE_CHOICE: [nav_cb, CallbackQueryHandler(listing_type_chosen, pattern="^listingtype_(free|paid)$"), MessageHandler(~filters.COMMAND, make_reminder(LISTING_TYPE_CHOICE))],
            RENTAL_TYPE_CHOICE: [nav_cb, CallbackQueryHandler(rental_type_chosen, pattern="^rentaltype_(uzoq_muddat|kunlik|dacha|mehmonxona)$"), MessageHandler(~filters.COMMAND, make_reminder(RENTAL_TYPE_CHOICE))],
            MANZIL: text_state(MANZIL),
            MOLJAL: text_state(MOLJAL),
            KIMLARGA: text_state(KIMLARGA),
            XONA: text_state(XONA),
            QULAYLIK: text_state(QULAYLIK),
            NARX: text_state(NARX),
            TELEFON: text_state(TELEFON),
            LOCATION_OPTIONAL: [
                MessageHandler(filters.LOCATION, location_received),
                MessageHandler(filters.StatusUpdate.WEB_APP_DATA, location_picked_via_webapp),
                MessageHandler(filters.Regex(f"^{re.escape(BTN_SKIP_LOCATION)}$"), location_skip),
                MessageHandler(filters.Regex(f"^{re.escape(BTN_LOCATION_BACK)}$"), location_back_to_telefon),
                MessageHandler(~filters.COMMAND, location_reminder),
            ],
            RASMLAR: [CallbackQueryHandler(rasm_back_to_location, pattern="^nav_back_to_location$"), nav_cb, CallbackQueryHandler(rasm_tayyor, pattern="^rasm_tayyor$"), MessageHandler(~filters.COMMAND, rasm_qabul)],
            SLIDESHOW_CONFIRM: [
                CallbackQueryHandler(slideshow_choice_router, pattern="^slideshow_(yes|no)$"),
                MessageHandler(~filters.COMMAND, slideshow_reminder),
            ],
            TASDIQLASH: [
                CallbackQueryHandler(tasdiqlash_ok, pattern="^tasdiqlash_ok$"),
                CallbackQueryHandler(tasdiqlash_nav_router, pattern="^(nav_back|nav_cancel)$"),
                MessageHandler(~filters.COMMAND, tasdiqlash_reminder),
            ],
            TOLOV_CHEK: [nav_cb, MessageHandler(~filters.COMMAND, tolov_chek_router)],
        },
        fallbacks=[nav_cb],
        name="elon_conv",
        persistent=False,
    )

    sub_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(BTN_SUBSCRIPTION)}$"), subscription_entry),
            CallbackQueryHandler(subscription_entry, pattern=r"^buy_subscription(_\d+)?$"),
            CommandHandler("start", subscription_entry, filters=filters.Regex(r"^/start buysub$")),
        ],
        states={
            SUB_WAIT_RECEIPT: [CallbackQueryHandler(sub_cancel_cb, pattern="^nav_cancel$"), MessageHandler(~filters.COMMAND, subscription_receipt)],
        },
        fallbacks=[CallbackQueryHandler(sub_cancel_cb, pattern="^nav_cancel$")],
        name="sub_conv",
        persistent=False,
    )

    check_phone_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(f"^{re.escape(BTN_CHECK_PHONE)}$"), check_phone_entry),
            CommandHandler("start", check_phone_entry, filters=filters.Regex(r"^/start checkphone$")),
        ],
        states={CHECK_PHONE_WAIT: [CallbackQueryHandler(check_phone_cancel, pattern="^nav_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, check_phone_receive)]},
        fallbacks=[CallbackQueryHandler(check_phone_cancel, pattern="^nav_cancel$")],
        name="check_phone_conv",
        persistent=False,
    )

    admin_reject_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_reject_start, pattern=r"^admin_reject_(listing|sub)_\d+$")],
        states={ADMIN_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_reject_reason), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(ADMIN_REASON))]},
        fallbacks=[CommandHandler("bekor", admin_reject_cancel)],
        name="admin_reject_conv",
        persistent=False,
    )

    admin_settings_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_setting_edit_start, pattern=r"^editset_\w+$")],
        states={ADMIN_SETTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_setting_value_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(ADMIN_SETTING_VALUE))]},
        fallbacks=[CommandHandler("bekor", admin_setting_cancel)],
        name="admin_settings_conv",
        persistent=False,
    )

    admin_block_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(block_new_entry, pattern="^block_new$")],
        states={
            ADMIN_BLOCK_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, block_phone_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(ADMIN_BLOCK_PHONE))],
            ADMIN_BLOCK_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, block_reason_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(ADMIN_BLOCK_REASON))],
        },
        fallbacks=[CommandHandler("bekor", block_flow_cancel)],
        name="admin_block_conv",
        persistent=False,
    )

    quick_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{re.escape(BTN_QUICK)}$"), quick_entry)],
        states={
            QUICK_TEXT: [CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, quick_text_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(QUICK_TEXT))],
            QUICK_PHONE: [CallbackQueryHandler(quick_phone_auto_router, pattern="^quick_phone_auto$"), CallbackQueryHandler(quick_phone_manual_router, pattern="^quick_phone_write$"), CallbackQueryHandler(quick_back_to_text, pattern="^quick_back_totext$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, quick_phone_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(QUICK_PHONE))],
            QUICK_MANZIL: [CallbackQueryHandler(quick_combined_auto_router, pattern="^quick_combined_auto$"), CallbackQueryHandler(quick_manzil_auto_router, pattern="^quick_manzil_auto$"), CallbackQueryHandler(quick_manzil_ai_router, pattern="^quick_manzil_ai$"), CallbackQueryHandler(quick_manzil_manual_router, pattern="^quick_manzil_write$"), CallbackQueryHandler(quick_back_to_phone, pattern="^quick_back_tophone$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, quick_manzil_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(QUICK_MANZIL))],
            QUICK_NARX: [CallbackQueryHandler(quick_narx_auto_router, pattern="^quick_narx_auto$"), CallbackQueryHandler(quick_narx_ai_router, pattern="^quick_narx_ai$"), CallbackQueryHandler(quick_narx_manual_router, pattern="^quick_narx_write$"), CallbackQueryHandler(quick_back_to_manzil, pattern="^quick_back_tomanzil$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, quick_narx_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(QUICK_NARX))],
            QUICK_PHOTOS: [CallbackQueryHandler(quick_back_to_narx, pattern="^quick_back_tonarx$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), CallbackQueryHandler(quick_rasm_tayyor, pattern="^quick_rasm_tayyor$"), MessageHandler(~filters.COMMAND, quick_rasm_qabul)],
            QUICK_CONFIRM: [CallbackQueryHandler(quick_back_to_photos, pattern="^quick_back_tophotos$"), CallbackQueryHandler(quick_post, pattern="^quick_post$"), CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$"), MessageHandler(~filters.COMMAND, quick_confirm_reminder)],
        },
        fallbacks=[CallbackQueryHandler(quick_cancel_cb, pattern="^quick_cancel$")],
        name="quick_conv",
        persistent=False,
    )

    ai_concierge_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{re.escape(BTN_AI_CONCIERGE)}$"), ai_concierge_entry)],
        states={AI_CONCIERGE_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_concierge_message), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(AI_CONCIERGE_CHAT))]},
        fallbacks=[CommandHandler("bekor", ai_concierge_cancel)],
        name="ai_concierge_conv",
        persistent=False,
    )

    mod_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(mod_add_entry, pattern="^mod_add$")],
        states={MOD_ADD_WAIT: [MessageHandler(filters.ALL & ~filters.COMMAND, mod_add_received)]},
        fallbacks=[CommandHandler("bekor", mod_add_cancel)],
        name="mod_add_conv",
        persistent=False,
    )

    admin_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_add_entry, pattern="^admin_add$")],
        states={ADMIN_ADD_WAIT: [MessageHandler(filters.ALL & ~filters.COMMAND, admin_add_received)]},
        fallbacks=[CommandHandler("bekor", admin_add_cancel)],
        name="admin_add_conv",
        persistent=False,
    )

    distalias_add_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(district_alias_add_entry, pattern=r"^distalias_add_\d+$")],
        states={DISTALIAS_ADD_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, district_alias_add_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(DISTALIAS_ADD_WAIT))]},
        fallbacks=[CommandHandler("bekor", district_alias_add_cancel)],
        name="distalias_add_conv",
        persistent=False,
    )

    usersearch_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex(f"^{re.escape(BTN_USER_SEARCH)}$") & filters.User(ADMIN_IDS), usersearch_entry)],
        states={USER_SEARCH_WAIT: [MessageHandler(filters.ALL & ~filters.COMMAND, usersearch_received)]},
        fallbacks=[CommandHandler("bekor", usersearch_cancel)],
        name="usersearch_conv",
        persistent=False,
    )

    addloc_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(addloc_entry, pattern="^addloc$")],
        states={LOCATION_WAIT: [CallbackQueryHandler(addloc_cancel, pattern="^nav_cancel$"), MessageHandler(filters.TEXT & ~filters.COMMAND, addloc_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(LOCATION_WAIT))]},
        fallbacks=[CallbackQueryHandler(addloc_cancel, pattern="^nav_cancel$")],
        name="addloc_conv",
        persistent=False,
    )

    edit_field_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(editfield_router, pattern=r"^editfield_\d+_\w+$")],
        states={EDIT_LISTING_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, editfield_value_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(EDIT_LISTING_VALUE))]},
        fallbacks=[CommandHandler("bekor", editfield_cancel)],
        name="edit_field_conv",
        persistent=False,
    )

    viewing_conv = ConversationHandler(
        entry_points=[CommandHandler("start", viewing_deeplink_entry, filters=filters.Regex(r"^/start viewing_\d+$"))],
        states={VIEWING_TIME_WAIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, viewing_time_received), MessageHandler(~filters.TEXT & ~filters.COMMAND, make_reminder(VIEWING_TIME_WAIT))]},
        fallbacks=[CommandHandler("bekor", viewing_time_cancel)],
        name="viewing_conv",
        persistent=False,
    )

    app.add_handler(elon_conv)
    register_conv("elon_conv", elon_conv)  # force_reset_conversation funksiyasi buni topa olishi uchun
    app.add_handler(sub_conv)
    register_conv("sub_conv", sub_conv)
    app.add_handler(check_phone_conv)
    register_conv("check_phone_conv", check_phone_conv)
    # MUHIM: viewing_conv o'zining "/start viewing_<id>" kirish nuqtasiga ega
    # (elon_conv/sub_conv/check_phone_conv kabi) - shuning uchun bu yerda,
    # GENERIK "start" handleridan (pastroqda) OLDIN ro'yxatdan o'tkazilishi
    # SHART, aks holda generik handler uni hech qachon ko'rmaydi.
    app.add_handler(viewing_conv)
    register_conv("viewing_conv", viewing_conv)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("fixbuttons", fixbuttons_command))
    app.add_handler(CommandHandler("setcategory", setcategory_command))
    app.add_handler(CommandHandler("postmap", postmap_command))
    app.add_handler(admin_reject_conv)
    app.add_handler(admin_settings_conv)
    app.add_handler(admin_block_conv)
    app.add_handler(quick_conv)
    app.add_handler(ai_concierge_conv)
    app.add_handler(mod_add_conv)
    app.add_handler(admin_add_conv)
    app.add_handler(distalias_add_conv)
    app.add_handler(usersearch_conv)
    app.add_handler(addloc_conv)
    app.add_handler(edit_field_conv)
    register_conv("edit_field_conv", edit_field_conv)
    app.add_handler(MessageHandler(
        filters.Regex(f"^({re.escape(BTN_LISTINGS)}|{re.escape(BTN_HELP)}|{re.escape(BTN_LOCATION_ALERT)}|{re.escape(BTN_MY_LOCATIONS)}|{re.escape(BTN_CHANNEL)}|{re.escape(BTN_STATS)}|{re.escape(BTN_SUBSCRIBERS)}|{re.escape(BTN_SETTINGS)}|{re.escape(BTN_PENDING)}|{re.escape(BTN_BLOCKED)}|{re.escape(BTN_MODERATORS)}|{re.escape(BTN_FLAGGED)}|{re.escape(BTN_LISTINGS_MAP)}|{re.escape(BTN_ADMIN_PANEL)}|{re.escape(BTN_SUBARENDA)}|{re.escape(BTN_DISTRICT_ALIASES)})$"),
        text_menu_router,
    ))
    app.add_handler(CallbackQueryHandler(admin_approve, pattern=r"^admin_approve_(listing|sub)_\d+$"))
    app.add_handler(CallbackQueryHandler(subpage_router, pattern=r"^subpage_\d+$"))
    app.add_handler(CallbackQueryHandler(usercard_router, pattern=r"^usercard_\d+$"))
    app.add_handler(CallbackQueryHandler(cardcancel_router, pattern=r"^cardcancel_\d+$"))
    app.add_handler(CallbackQueryHandler(cardcancelyes_router, pattern=r"^cardcancelyes_\d+$"))
    app.add_handler(CallbackQueryHandler(cardban_router, pattern=r"^cardban_\d+$"))
    app.add_handler(CallbackQueryHandler(cardunban_router, pattern=r"^cardunban_\d+$"))
    app.add_handler(CallbackQueryHandler(flagpage_router, pattern=r"^flagpage_\d+$"))
    app.add_handler(CallbackQueryHandler(statsperiod_router, pattern=r"^statsperiod_(daily|weekly|monthly|yearly)$"))
    app.add_handler(CallbackQueryHandler(fraudban_router, pattern=r"^fraudban_(\d+|skip)$"))
    app.add_handler(CallbackQueryHandler(blockpage_router, pattern=r"^blockpage_\d+$"))
    app.add_handler(CallbackQueryHandler(unblock_router, pattern=r"^unblock_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(blockask_router, pattern=r"^blockask_(yes|no)_\d+$"))
    app.add_handler(CallbackQueryHandler(toggle_setting_router, pattern=r"^toggleset_\w+$"))
    app.add_handler(CallbackQueryHandler(mod_remove_router, pattern=r"^modremove_\d+$"))
    app.add_handler(CallbackQueryHandler(mod_toggle_super_router, pattern=r"^modsuper_\d+$"))
    app.add_handler(CallbackQueryHandler(district_alias_view_router, pattern=r"^distalias_view_\d+$"))
    app.add_handler(CallbackQueryHandler(district_alias_back_router, pattern=r"^distalias_back$"))
    app.add_handler(CallbackQueryHandler(district_alias_remove_router, pattern=r"^distaliasrm_\d+_\d+$"))
    app.add_handler(CallbackQueryHandler(quickteach_skip_router, pattern=r"^quickteach_skip$"))
    app.add_handler(CallbackQueryHandler(admin_remove_router, pattern=r"^adminremove_\d+$"))
    app.add_handler(CallbackQueryHandler(stillavail_router, pattern=r"^stillavail_(yes|no)_\d+$"))
    app.add_handler(CallbackQueryHandler(complain_reason_router, pattern=r"^rpt_(rented|fake|noresponse|fraud|cancel)_\d+$"))
    app.add_handler(CallbackQueryHandler(channel_phone_button, pattern=r"^chphone_\d+$"))
    app.add_handler(CallbackQueryHandler(channel_complain_button, pattern=r"^chcomplain_\d+$"))
    app.add_handler(CallbackQueryHandler(channel_elon_button, pattern="^chelon$"))
    app.add_handler(CallbackQueryHandler(channel_buysub_button, pattern="^chbuysub$"))
    app.add_handler(CallbackQueryHandler(channel_checkphone_button, pattern="^chcheckphone$"))
    app.add_handler(CallbackQueryHandler(staleconfirm_router, pattern=r"^staleconfirm_\d+$"))
    app.add_handler(CallbackQueryHandler(staleignore_router, pattern=r"^staleignore_\d+$"))
    app.add_handler(CallbackQueryHandler(fraudblock_router, pattern=r"^fraudblock_\d+$"))
    app.add_handler(CallbackQueryHandler(selfexpire_router, pattern=r"^selfexpire_\d+$"))
    app.add_handler(CallbackQueryHandler(editlisting_entry, pattern=r"^editlisting_\d+$"))
    app.add_handler(CallbackQueryHandler(editcancelmenu_router, pattern=r"^editcancelmenu_\d+$"))
    app.add_handler(CallbackQueryHandler(deletelisting_entry, pattern=r"^deletelisting_\d+$"))
    app.add_handler(CallbackQueryHandler(deletelisting_confirm_router, pattern=r"^deletelistingyes_\d+$"))
    app.add_handler(CallbackQueryHandler(viewingaccept_router, pattern=r"^viewingaccept_\d+$"))
    app.add_handler(CallbackQueryHandler(viewingdecline_router, pattern=r"^viewingdecline_\d+$"))
    app.add_handler(CallbackQueryHandler(delloc_router, pattern=r"^delloc_\d+$"))
    app.add_handler(CallbackQueryHandler(help_topic_router, pattern=r"^help_(elon|limit|check|mening|hudud)$"))
    app.add_handler(CallbackQueryHandler(help_back_router, pattern="^help_back$"))
    app.add_handler(CallbackQueryHandler(blockcard_router, pattern=r"^blockcard_\d+_\d+$"))
    app.add_error_handler(error_handler)

    if app.job_queue:
        app.job_queue.run_daily(job_expiry_reminders, time=dtime(hour=9, minute=0, tzinfo=TASHKENT_TZ))
        app.job_queue.run_monthly(job_monthly_report, when=dtime(hour=9, minute=0, tzinfo=TASHKENT_TZ), day=1)
        app.job_queue.run_daily(job_daily_backup, time=dtime(hour=4, minute=0, tzinfo=TASHKENT_TZ))
        app.job_queue.run_daily(job_morning_digest, time=dtime(hour=8, minute=45, tzinfo=TASHKENT_TZ))
        app.job_queue.run_daily(job_stale_check, time=dtime(hour=10, minute=0, tzinfo=TASHKENT_TZ))
        # job_promote_limit va job_repost_paid_listings o'zlari admin
        # sozlagan oraliqni (promote_limit_interval_hours /
        # paid_repost_interval_hours, Sozlamalar) hisobga olib ishlaydi -
        # shuning uchun bu yerda har 30 daqiqada tekshirib turamiz, ular esa
        # oxirgi joylashdan buyon yetarli vaqt o'tmagan bo'lsa hech narsa
        # qilmasdan chiqib ketishadi. Admin oraliqni o'zgartirsa, botni
        # qayta ishga tushirmasdan, keyingi tekshiruvda kuchga kiradi.
        app.job_queue.run_repeating(job_promote_limit, interval=1800, first=60)
        app.job_queue.run_repeating(job_repost_paid_listings, interval=1800, first=90)
        app.job_queue.run_daily(job_weekly_top_location, time=dtime(hour=9, minute=0, tzinfo=TASHKENT_TZ), days=(0,))
        app.job_queue.run_daily(job_empty_region_alert, time=dtime(hour=11, minute=0, tzinfo=TASHKENT_TZ))
    else:
        logger.warning("JobQueue mavjud emas \u2014 eslatma va oylik hisobot ishlamaydi. O'rnating: pip install \"python-telegram-bot[job-queue]\"")

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()


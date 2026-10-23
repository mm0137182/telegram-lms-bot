#!/usr/bin/env python3
"""
Telegram → Hermes Bot Integration
Polls Telegram for messages, stores them for Hermes to process.
Run via cronjob every 30 seconds.
"""

import urllib.request
import urllib.error
import json
import os
import time
import difflib
from datetime import datetime
from pathlib import Path

# Configuration
TOKEN = "8658185373:AAGrVY2zqKK2sDK_x76UNQGob1JRxgBYlZc"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

SCRATCH_DIR = Path(os.environ.get("BOT_DATA_DIR", str(Path(__file__).parent)))
COMMANDS_FILE = SCRATCH_DIR / "telegram_commands.json"
CONFIG_FILE = SCRATCH_DIR / ".hermes" / "secrets" / "telegram_config.json"
FILES_DIR = SCRATCH_DIR / "telegram_uploads"  # Downloaded files from Telegram
FILES_DIR.mkdir(parents=True, exist_ok=True)

# Valid commands for Hermes (LMS integration)
COMMANDS = {
    "افتح المنصة": "lms_open",
    "فتح المنصة": "lms_open",
    "البريد الإلكتروني": "lms_email",
    "تحقق من الحالة": "lms_status",
    "الحصص التفاعلية": "lms_sessions",
    "رفع ملف": "lms_upload",
    "مساعدة": "help",
    "الأوامر": "help",
    "start": "help",
    "/start": "help",
    "help": "help",
    "hi": "help",
    "مرحبا": "help",
}


# Poll configuration — short polling to avoid orphaned long-polls causing 409
POLL_TIMEOUT = 10  # Telegram long-poll timeout (10s max to avoid 409 stale locks)
HTTP_TIMEOUT = 15  # General HTTP timeout


def http_get_json(url, timeout=HTTP_TIMEOUT):
    """HTTP GET request expecting JSON response"""
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout)
        body = resp.read()
        resp.close()
        return json.loads(body.decode('utf-8'))
    except urllib.error.HTTPError as e:
        # CRITICAL: read+close the error body so the TCP connection is released
        # on the server side — prevents orphaned long-polls that cause 409 on subsequent calls
        try:
            e.read()
        except Exception:
            pass
        try:
            e.close()
        except Exception:
            pass
        print(f"  خطأ في الاتصال: HTTP Error {e.code}: {e.reason}")
        return {"ok": False, "status_code": e.code, "result": []}
    except json.JSONDecodeError:
        # Response is not JSON (e.g., HTML page) — treat as reachable
        return {"ok": True, "status_code": 200, "is_html": True}
    except Exception as e:
        print(f"  خطأ في الاتصال: {e}")
        return {"ok": False, "result": []}


def http_get(url, timeout=HTTP_TIMEOUT):
    """HTTP GET request — returns dict with 'ok', 'status_code', etc."""
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout)
        status_code = resp.getcode()
        body = resp.read()
        # Try JSON first
        try:
            return {"ok": True, "status_code": status_code, "json": json.loads(body.decode('utf-8'))}
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Not JSON — return status info
            return {"ok": True, "status_code": status_code, "is_html": True}
    except urllib.error.HTTPError as e:
        return {"ok": False, "status_code": e.code}
    except Exception as e:
        print(f"  خطأ في الاتصال: {e}")
        return {"ok": False, "status_code": None}


def http_post(url, data_dict, timeout=15):
    """HTTP POST request using urllib"""
    try:
        data = json.dumps(data_dict).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        resp = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"  خطأ في الإرسال: {e}")
        return {"ok": False}


def load_config():
    """Load saved configuration"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {"token": TOKEN, "user_chat_id": None}


def save_config(config):
    """Save configuration"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)


def load_commands():
    """Load pending commands from file"""
    if COMMANDS_FILE.exists():
        with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"last_update_id": 0, "pending": [], "processed": []}


def save_commands(data):
    """Save commands to file"""
    with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_updates(offset=None):
    """Poll Telegram for new updates (long polling)"""
    url = f"{BASE_URL}/getUpdates?timeout={POLL_TIMEOUT}&limit=50"
    if offset:
        url += f"&offset={offset}"
    result = http_get_json(url, timeout=POLL_TIMEOUT + 5)
    # Retry on 409 Conflict (orphaned long-poll from a previous process instance)
    if not result.get("ok") and result.get("status_code") == 409:
        for attempt in range(3):
            print(f"  ⚠️ 409 Conflict — retry {attempt + 1}/3 بعد 5 ث...")
            time.sleep(5)
            result = http_get_json(url, timeout=POLL_TIMEOUT + 5)
            if result.get("ok"):
                break
    return result


def send_message(chat_id, text):
    """Send a message back to the user via Telegram"""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    result = http_post(f"{BASE_URL}/sendMessage", payload, timeout=15)
    return result.get("ok", False)


def download_telegram_file(file_path_param, timeout=60):
    """Download a file from Telegram's servers using file_path token"""
    url = f"https://api.telegram.org/file/bot{TOKEN}/{file_path_param}"
    try:
        req = urllib.request.Request(url)
        resp = urllib.request.urlopen(req, timeout=timeout)
        return resp.read(), resp.headers
    except Exception as e:
        print(f"  خطأ في تحميل الملف: {e}")
        return None, None


def handle_document(message, chat_id, from_user):
    """Download and store a document file from Telegram"""
    document = message.get("document", {})
    file_id = document.get("file_id", "")
    file_name = document.get("file_name", "unnamed_file.bin")
    file_size = document.get("file_size", 0)

    if not file_id:
        return None

    print(f"  📎 استقبلت ملف: {file_name} ({file_size} بايت)")

    # Step 1: get file_path via getFile API
    resp = http_post(f"{BASE_URL}/getFile", {"file_id": file_id}, timeout=15)
    if not resp.get("ok"):
        send_message(chat_id, "❌ خطأ في الحصول على الملف من تيليجرام")
        return None

    file_path = resp["result"]["file_path"]
    # Step 2: download the file content
    file_data, headers = download_telegram_file(file_path, timeout=60)
    if file_data is None:
        send_message(chat_id, "❌ فشل تحميل الملف")
        return None

    # Step 3: save locally
    safe_name = file_name.replace("/", "_").replace("\\", "_").replace(":", "_")
    local_path = FILES_DIR / f"{int(time.time())}_{safe_name}"
    with open(local_path, "wb") as f:
        f.write(file_data)

    size_mb = file_size / (1024 * 1024) if file_size else 0
    print(f"  ✅ حُفظ الملف: {local_path}")

    # Send confirmation
    preview_link = f"تم الحفظ: {local_path.name}"
    send_message(chat_id,
        f"✅ <b>تم استقبال الملف!</b>\n\n"
        f"📎 الاسم: {file_name}\n"
        f"📏 الحجم: {size_mb:.1f} MB\n"
        f"💾 {preview_link}\n\n"
        f"🔄 <b>جارٍ تحضيره للرفع على المنصة...</b>")

    # Return file info for upload processing
    return {
        "file_id": file_id,
        "file_name": file_name,
        "file_path": str(local_path),
        "file_size": file_size,
        "chat_id": chat_id,
        "user": from_user.get("first_name", ""),
        "timestamp": datetime.now().isoformat(),
    }


def match_command(text):
    """Smart command matching with fuzzy + keyword intent detection"""
    text_lower = text.lower().strip()

    # 1. Exact match
    for cmd_key, cmd_value in COMMANDS.items():
        if text_lower == cmd_key.lower():
            return cmd_value, 1.0

    # 2. Startswith match
    for cmd_key, cmd_value in COMMANDS.items():
        if text_lower.startswith(cmd_key.lower()):
            return cmd_value, 0.9

    # 3. Fuzzy match (closest command)
    all_keys = list(COMMANDS.keys())
    matches = difflib.get_close_matches(text_lower, [k.lower() for k in all_keys], n=1, cutoff=0.3)
    if matches:
        best = matches[0]
        cmd_value = COMMANDS[all_keys[[k.lower() for k in all_keys].index(best)]]
        return cmd_value, 0.7

    # 4. Keyword-based intent detection
    intent_map = {
        ("منصة", "لوحة", "دخول", "login", "platform", "ادخل", "فتح"): ("lms_open", 0.6),
        ("بريد", "ايميل", "email", "رسائل", "إيميلات"): ("lms_email", 0.6),
        ("حالة", "حاله", "وضعية", "status", "موقع", "service"): ("lms_status", 0.6),
        ("حصص", "حصة", "جدول", "schedule", " timetable", "مواعيد"): ("lms_sessions", 0.6),
        ("ملف", "رفع", "upload", "attach", "مستند", "ورقة"): ("lms_upload", 0.6),
        ("مساعدة", "help", "كيف", "ازاي", "شرح", "أوامر"): ("help", 0.6),
        # Teacher-specific intents
        ("تفاعلية", "تفاعلي", "حصة تفاعلية", "interactive"): ("lms_sessions", 0.8),
        ("اختبار", "exam", "test", "سؤال", "اسألة"): ("help", 0.5),
        ("طلاب", "student", "معلم", "teacher", "صف"): ("help", 0.5),
        ("واجب", "homework", "واجبات"): ("help", 0.5),
    }
    for keywords, (cmd, confidence) in intent_map.items():
        for kw in keywords:
            if kw in text_lower:
                return cmd, confidence

    return None, 0.0


def generate_ai_response(text, chat_id, confidence=0.0):
    """Generate an intelligent response for ANY input — no command required"""
    text_lower = text.lower().strip()
    user_name = load_config().get("user_name", "المستخدم")

    # Match to known command
    matched_cmd, conf = match_command(text)

    if matched_cmd and matched_cmd != "help":
        result_msg = execute_command(matched_cmd, chat_id)
        if result_msg:
            return f"✅ الأمر: {text}\n\n{result_msg}", matched_cmd, conf

    # If no command but keywords detected
    if matched_cmd == "help" and conf > 0.4:
        return (
            f"👋 مرحباً {user_name}!\n\n"
            f"شبيه جداً بـ 'مساعدة' — إليك ما يتوفره البوت:\n\n"
            "• <b>فتح المنصة</b> — يفتح الـ LMS\n"
            "• <b>البريد الإلكتروني</b> — يفتح صفحة البريد\n"
            "• <b>تحقق من الحالة</b> — يتحقق من حالة المنصة\n"
            "• <b>الحصص التفاعلية</b> — يفتح جدول الحصص\n"
            "• <b>رفع ملف</b> — يبدأ رفع ملف\n\n"
            "أو أرسل أي سؤال وسأساعدك!",
            "help", conf
        )

    # AI-style intelligent response for unrecognized input
    # Build a contextual response based on keywords in the user's message
    keywords = text_lower.split()

    # Detect what the user might want
    detected_intents = []
    if any(w in text_lower for w in ["منصة", "لوحة", "login", "دخول", "ادخل"]):
        detected_intents.append("الوصول للمنصة")
    if any(w in text_lower for w in ["بريد", "ايميل", "رسائل"]):
        detected_intents.append("البريد الإلكتروني")
    if any(w in text_lower for w in ["حالة", "وضعية", "موقع"]):
        detected_intents.append("فحص حالة المنصة")
    if any(w in text_lower for w in ["حصص", "جدول", "مواعيد", "تفاعلية"]):
        detected_intents.append("جدول الحصص التفاعلية")
    if any(w in text_lower for w in ["ملف", "رفع", "upload", "ورقة", "مستند"]):
        detected_intents.append("رفع ملف")
    if any(w in text_lower for w in ["مساعدة", "ازاي", "شرح", "أمر", "طريقة"]):
        detected_intents.append("الحصول على المساعدة")

    if detected_intents:
        suggestions = "\n".join(f"  • {intent}" for intent in detected_intents)
        return (
            f"🤖 <b>أفهم طلبك!</b>\n\n"
            f"ظننت إنك تريد: {', '.join(detected_intents)}\n\n"
            f"جرّب أحد هذه:\n{suggestions}\n\n"
            f"أو أرسل 'مساعدة' لكل الأوامر المتاحة.",
            None, 0.3
        )

    # Fully general AI-style response
    responses = {
        "greeting": "👋 مرحباً! أنا Hermes Bot — جاهز أساعدك في لوحة التقدم الخاصة بك. جرب 'مساعدة'!",
        "unknown": f"🤔 أنا Hermes Bot — مش فاهم بالضبط إيه عاوزه.\n\nلكن أقدر أساعدك في:\n• فتح المنصة\n• البريد الإلكتروني\n• تحقق من الحالة\n• الحصص التفاعلية\n• رفع ملف\n\nأو أرسل 'مساعدة' وهأشرح لك كل حاجة.",
    }

    if any(w in text_lower for w in ["مرحبا", "مرحباً", "اهلا", "اهلاً", "hi", "hello", "سلام"]):
        reply = responses["greeting"]
    elif any(w in text_lower for w in ["شكرا", "شكراً", "شكرا", "thanks", "كفاية", "تمام"]):
        reply = "يسعدني أساعدك! 🌟 هل تحتاج حاجة تانية؟"
    elif any(w in text_lower for w in ["شغال", "توكل", "كيف", "ازي"]):
        reply = "✅ نعم، جاهز! كل الأوامر شغالة. جرب 'فتح المنصة' أو أرسل ملف."
    elif any(w in text_lower for w in ["بوت", "انت", "هوا"]):
        reply = "🤖 أنا Hermes Bot — بوت التواصل مع المنصة. متصل بـ LMS وجاهز أساعدك دايمًا."
    else:
        reply = responses["unknown"]

    return reply, None, 0.1


def process_updates():
    """Check for new messages and store them"""
    config = load_config()
    commands = load_commands()

    last_id = commands.get("last_update_id", 0)
    resp = get_updates(last_id + 1)

    new_messages = 0

    if resp.get("ok") and resp.get("result"):
        for update in resp["result"]:
            update_id = update["update_id"]
            message = update.get("message", {})
            text = message.get("text", "").strip()
            chat = message.get("chat", {})
            chat_id = chat.get("id")
            from_user = message.get("from", {})

            if not chat_id:
                continue

            document = message.get("document")
            if document and document.get("file_id"):
                file_info = handle_document(message, chat_id, from_user)
                if file_info:
                    file_info["update_id"] = update_id
                    file_info["status"] = "pending_upload"
                    commands.setdefault("uploads", []).append(file_info)
                
                # ALWAYS update last_update_id to prevent reprocessing same message
                commands["last_update_id"] = update_id
                save_commands(commands)
                continue

            if not text:
                continue

            # Save chat_id if not already saved
            if not config.get("user_chat_id"):
                config["user_chat_id"] = chat_id
                config["user_name"] = f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}"
                save_config(config)
                # Send welcome message
                send_message(chat_id,
                    "✅ <b>مرحباً!</b> البوت متصل بـ Hermes بنجاح.\n\n"
                    "الأوامر المتاحة:\n"
                    " • <b>فتح المنصة</b> — يفتح الـ LMS\n"
                    " • <b>البريد الإلكتروني</b> — يفتح صفحة البريد\n"
                    " • <b>تحقق من الحالة</b> — يتحقق من حالة المنصة\n"
                    " • <b>الحصص التفاعلية</b> — يفتح جدول الحصص\n"
                    " • <b>رفع ملف</b> — يبدأ رفع ملف\n"
                    " • <b>مساعدة</b> — يعرض هذه القائمة\n\n"
                    "أرسل أي أمر الآن وسأنفذه!")
                print(f"  👋 مرحباً بـ {config.get('user_name', 'المستخدم')} (chat_id={chat_id})")

            # Check if it's a recognized command
            matched_cmd = None
            for cmd_key, cmd_value in COMMANDS.items():
                if text.lower() == cmd_key.lower() or text.lower().startswith(cmd_key.lower()):
                    matched_cmd = cmd_value
                    break

            # Store the message as a pending command
            new_msg = {
                "update_id": update_id,
                "text": text,
                "command": matched_cmd,
                "chat_id": chat_id,
                "user": from_user.get("first_name", ""),
                "timestamp": datetime.now().isoformat(),
                "status": "pending",
            }
            commands["pending"].append(new_msg)
            new_messages += 1

            # Auto-execute known commands immediately
            if matched_cmd and matched_cmd != "help":
                result_msg = execute_command(matched_cmd, chat_id)
                if result_msg:
                    send_message(chat_id, f"✅ الأمر: {text}\n\n{result_msg}")
                    new_msg["status"] = "replied"
                    print(f"  ✅ تم الرد على: '{text}'")
                else:
                    new_msg["status"] = "failed"
            else:
                # AI: generate intelligent response for help or unknown messages
                ai_reply, ai_cmd, ai_conf = generate_ai_response(text, chat_id)
                send_message(chat_id, ai_reply)
                new_msg["command"] = ai_cmd or matched_cmd
                new_msg["ai_confidence"] = ai_conf
                new_msg["status"] = "replied"
                print(f"  🤖 رد ({ai_conf:.1f}): '{text[:40]}'")

            commands["last_update_id"] = update_id

        save_commands(commands)

    if new_messages > 0:
        print(f"  استلمت {new_messages} رسالة/رسائل جديدة")

    return new_messages


def execute_command(cmd, chat_id):
    """Execute a command locally"""
    if cmd == "lms_open":
        result = http_get("https://lms.ibnroshd.edu.sa/auth/login", timeout=10)
        if result and result.get("ok"):
            return "✅ <b>المنصة متاحة وجاهزة!</b>\n\n• الرابط: https://lms.ibnroshd.edu.sa/auth/login\n\nHermes جاهز للاتصال بالمنصة."
        else:
            return "⚠️ المنصة غير متاحة الآن — جرّب مرة أخرى في لحظات"
    elif cmd == "lms_email":
        return "📬 <b>تم توجيهك لصفحة البريد الإلكتروني</b>\n\nاستخدم البوت لتلقي رسائل البريد وإدارتها."
    elif cmd == "lms_status":
        result = http_get("https://apicore.ibnroshd.edu.sa/api/Common/GetSessionContext", timeout=10)
        if result and result.get("ok"):
            return "✅ <b>خوادر المنصة تعمل بصورة طبيعية</b>"
        else:
            return "❌ غير قادر على الوصول للمنصة حالياً"
    elif cmd == "lms_sessions":
        return "📅 <b>تم الوصول إلى جدول الحصص التفاعلية</b>\n\nلفتح جدول الحصص: https://lms.ibnroshd.edu.sa/Teacher/Dashboard"
    elif cmd == "lms_upload":
        return "📎 <b>جاهز لاستقبال الملف</b>\n\nأرسل أي ملف (PDF، Word، Excel) وسأرفعه على المنصة تلقائياً. سيتم إرسال إشعار بالنتيجة بعد الرفع."
    return None


def main():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] فحص رسائل التليجرام...")
    count = process_updates()

    # Also retry any pending commands from previous runs
    commands = load_commands()
    if commands.get("pending"):
        print("  إعادة محاولة الأوامر المعلقة...")
        config = load_config()
        default_chat_id = config.get("user_chat_id")
        for cmd in commands.get("pending", []):
            msg_text = cmd.get("text", "")
            cmd_chat_id = cmd.get("chat_id", default_chat_id)

            # Re-match using smart matching
            matched_cmd, _ = match_command(msg_text)

            if matched_cmd and matched_cmd != "help":
                result_msg = execute_command(matched_cmd, cmd_chat_id)
                if result_msg:
                    send_message(cmd_chat_id, f"✅ الأمر: {msg_text}\n\n{result_msg}")
                    cmd["status"] = "replied"
                    print(f"  ✅ إعادة الرد على: '{msg_text}'")
            else:
                # AI response for help or unrecognized
                ai_reply, ai_cmd, ai_conf = generate_ai_response(msg_text, cmd_chat_id)
                send_message(cmd_chat_id, ai_reply)
                cmd["status"] = "replied"
                print(f"  🤖 إعادة رد ({ai_conf:.1f}): '{msg_text[:40]}'")

        commands["pending"] = [c for c in commands.get("pending", []) if c.get("status") != "replied"]
        save_commands(commands)

    print(f"  الرسائل الجديدة: {count}")

    # Process pending file uploads to LMS
    ok, num = upload_pending_files()
    if num > 0:
        print(f"  📤 معالجة {num} رفع(ات) للمنصة")


def upload_pending_files():
    """Process files with 'pending_upload' status by uploading to LMS API."""
    commands = load_commands()
    uploads = commands.get("uploads", [])
    
    if not uploads:
        return True, 0
    
    pending = [u for u in uploads if u.get("status") == "pending_upload"]
    if not pending:
        return True, 0
    
    # Load token
    token_path = SCRATCH_DIR / "lms_token.json"
    try:
        with open(token_path) as f:
            token_data = json.load(f)
        token = token_data['content']['token']
        school_id = token_data['content'].get('schoolID', 20)
    except Exception as e:
        print(f"  ❌ لا يمكن تحميل رمز الوثيقة: {e}")
        return False, 0
    
    # Get user profile for metadata
    user_info = http_get_json(f"https://apicore.ibnroshd.edu.sa/api/Common/GetUserInfo?EducationalYearID=5")
    employee_id = 5816
    teacher_id = 6600
    user_group_id = 3
    subject_id = 0
    
    if user_info.get("code") == "200":
        content = user_info.get("content", {})
        emp = content.get("employeeProfileDTO", {})
        employee_id = emp.get("employeeID", employee_id)
        teacher_id = emp.get("teacherID", teacher_id)
        user_group_id = content.get("userGroupID", user_group_id)
    
    # Try to get teacher's subject ID
    subjects = http_get_json(f"https://apicore.ibnroshd.edu.sa/api/Common/GetTeacherSubjectsWithSections?EmployeeID={employee_id}&educationalYearID=5&SemesterID=1&PerSection=true")
    if subjects.get("code") == "200":
        subject_list = subjects.get("content", [])
        if subject_list:
            subject_id = subject_list[0].get("schoolDivisionGradeSubjectID", 0)
    
    log_file = SCRATCH_DIR / "upload_processor.log"
    
    processed = 0
    for upload in pending:
        file_path = upload.get("file_path")
        chat_id = upload.get("chat_id")
        file_name = upload.get("file_name", "ملف")
        file_size = upload.get("file_size", 0)
        
        if not file_path or not os.path.exists(file_path):
            upload["status"] = "failed"
            upload["error"] = "الملف غير موجود"
            processed += 1
            continue
        
        print(f"  📤 جارٍ رفع: {file_name}")
        
        # Build metadata matching Angular app's WI class
        metadata = {
            "CreatorID": employee_id,
            "EmployeeID": employee_id,
            "FileDescription": "",
            "GroupID": user_group_id,
            "ModuleTypeID": 2,
            "SchoolDivisionGradeSubjectID": subject_id,
            "TeacherID": teacher_id,
            "ModuleID": 0,
        }
        
        data_json = json.dumps(metadata)
        
        # Build multipart body
        with open(file_path, "rb") as f:
            file_data = f.read()
        
        ext = file_name.rsplit(".", 1)[-1].lower()
        content_types = {
            "pdf": "application/pdf",
            "doc": "application/msword",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "xls": "application/vnd.ms-excel",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        }
        ct = content_types.get(ext, "application/octet-stream")
        
        boundary = "----WebKitFormBoundary7MA4YW9e2ZMwYP"
        body = b""
        body += f"--{boundary}\r\n".encode()
        body += 'Content-Disposition: form-data; name="data"\r\n\r\n'.encode()
        body += f"{data_json}\r\n".encode()
        body += f"--{boundary}\r\n".encode()
        body += f'Content-Disposition: form-data; name="File"; filename="{file_name}"\r\n'.encode()
        body += f"Content-Type: {ct}\r\n\r\n".encode()
        body += file_data
        body += b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        
        url = "https://apicore.ibnroshd.edu.sa/api/Common/UploadFiles"
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("x-school-id", str(school_id))
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            result = json.loads(resp.read().decode("utf-8"))
            upload["status"] = "uploaded"
            upload["uploaded_at"] = datetime.now().isoformat()
            upload["result"] = result
            size_mb = file_size / (1024*1024) if file_size else 0
            send_message(chat_id,
                f"✅ تم رفع الملف بنجاح!\n📎 {file_name}\n📏 {size_mb:.1f} MB"
            )
            print(f"  ✅ نجح الرفع: {file_name}")
        except urllib.error.HTTPError as e:
            body_resp = e.read().decode("utf-8", errors="replace")
            try:
                err = json.loads(body_resp)
                error_msg = err.get("message", body_resp)
            except:
                error_msg = body_resp[:200]
            
            upload["status"] = "failed"
            upload["error"] = error_msg
            upload["failed_at"] = datetime.now().isoformat()
            
            if "Res_Error" in error_msg:
                user_msg = (f"⚠️ <b>فشل الرفع على المنصة</b>\n\n"
                           f"📎 {file_name}\n"
                           f"⚠️ Res_Error — قد يكون الرمز منتهي أو المنصة مضطربة. "
                           f"جرّب تسجيل الدخول مرة أخرى على المنصة.")
            else:
                user_msg = f"❌ <b>فشل رفع الملف</b>\n\n📎 {file_name}\n⚠️ {error_msg[:150]}"
            
            send_message(chat_id, user_msg)
            print(f"  ❌ فشل الرفع: {error_msg}")
        except Exception as e:
            upload["status"] = "failed"
            upload["error"] = str(e)[:200]
            send_message(chat_id, f"❌ <b>خطأ في اتصال المنصة</b>\n\n📎 {file_name}\n⚠️ {str(e)[:150]}")
            print(f"  ❌ خطأ اتصال: {e}")
        
        processed += 1
        
        # Log to upload_processor.log
        try:
            with open(log_file, "a") as lf:
                ts = datetime.now().strftime("%H:%M:%S")
                lf.write(f"[{ts}] {file_name}: {upload.get('status', 'unknown')}\n")
        except:
            pass
    
    # Save updated state (commands dict was modified in-place via upload references)
    save_commands(commands)
    return True, processed


if __name__ == "__main__":
    import sys
    # Lock mechanism prevents daemon + cronjob from causing 409 conflicts
    LOCK_FILE = SCRATCH_DIR / "telegram_poller.lock"

    def is_pid_alive(pid):
        """Check if a PID is alive — uses tasklist on Windows for reliability.
        On Windows, os.kill(pid, 0) can raise OSError: [WinError 87] for alive
        processes, causing false 'dead' detection. tasklist is reliable."""
        try:
            import subprocess
            result = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}'],
                capture_output=True, text=True, timeout=5
            )
            return str(pid) in result.stdout
        except Exception:
            pass
        # Fallback to os.kill (Unix-like systems)
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, OverflowError):
            return False
        except PermissionError:
            return True
        except Exception:
            return False

    def acquire_lock():
        # ATOMIC lock — uses O_CREAT|O_EXCL to prevent race condition
        # between daemon and cronjob both seeing no lock file
        try:
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            print(f"  [LOCK] Acquired (PID={os.getpid()})")
            return True
        except FileExistsError:
            pass
        # Lock file exists — check if process is still alive
        try:
            old_pid = int(LOCK_FILE.read_text().strip())
            if is_pid_alive(old_pid):
                print(f"  🔒 Another poller is running (PID {old_pid}) — skipping")
                return False
            print(f"  [LOCK] Stale lock (PID {old_pid} dead) — taking over")
        except (ValueError, ProcessLookupError, OverflowError):
            pass
        # Stale lock — take over (overwrite PID)
        LOCK_FILE.write_text(str(os.getpid()))
        print(f"  [LOCK] Lock taken over (PID={os.getpid()})")
        return True

    def release_lock():
        # DON'T delete lock file — let it persist for PID checking
        # This prevents race conditions where lock file is deleted
        # and next cronjob run starts without checking
        pass

    if "--daemon" in sys.argv:
        if not acquire_lock():
            print("🔒 Another poller is already running — exiting daemon mode")
            sys.exit(0)
        print("[DAEMON] بدأ التشغيل المستمر (Ctrl+C للإيقاف)")
        try:
            while True:
                try:
                    main()
                except Exception as e:
                    print(f"[DAEMON] خطأ: {e}")
                time.sleep(1)
        finally:
            release_lock()
    else:
        if not acquire_lock():
            print("🔒 Daemon is already running — cronjob skipping")
            sys.exit(0)
        try:
            main()
        finally:
            release_lock()
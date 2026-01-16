"""
Google One (Gemini) Student Verification Bot
Telegram Bot untuk Railway Deployment
With Student ID Card Generator Integration

Author: ThanhNguyxn
Modified: January 2026
"""

import os
import re
import json
import time
import random
import hashlib
from io import BytesIO
from typing import Dict, Optional, List
from pathlib import Path

import httpx
from telebot import TeleBot, types
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# ============ CONFIG ============
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable required!")

ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

PROGRAM_ID = "67c8c14f5f17a83b745e3f82"
SHEERID_API_URL = "https://services.sheerid.com/rest/v2"
ORG_SEARCH_URL = "https://orgsearch.sheerid.net/rest/organization/search"
ID_CARD_API_URL = "https://id-livid-phi.vercel.app/generate"

MIN_DELAY = 300
MAX_DELAY = 800

bot = TeleBot(BOT_TOKEN, parse_mode="HTML")

# User sessions
user_sessions = {}

# Stats
class Stats:
    def __init__(self):
        self.file = Path("stats.json")
        self.data = self._load()

    def _load(self):
        if self.file.exists():
            try:
                return json.loads(self.file.read_text())
            except:
                pass
        return {"total": 0, "success": 0, "failed": 0, "orgs": {}}

    def _save(self):
        self.file.write_text(json.dumps(self.data, indent=2))

    def record(self, org: str, success: bool):
        self.data["total"] += 1
        self.data["success" if success else "failed"] += 1
        if org not in self.data["orgs"]:
            self.data["orgs"][org] = {"success": 0, "failed": 0}
        self.data["orgs"][org]["success" if success else "failed"] += 1
        self._save()

    def get_summary(self) -> str:
        total = self.data["total"]
        success = self.data["success"]
        failed = self.data["failed"]
        rate = (success / total * 100) if total else 0

        # Top 5 universities
        orgs_sorted = sorted(self.data["orgs"].items(), 
                           key=lambda x: x[1]["success"], reverse=True)[:5]

        top_unis = "\n".join([f"  • {org}: {data['success']} success" 
                              for org, data in orgs_sorted]) if orgs_sorted else "  No data yet"

        return f"""📊 <b>Statistics</b>

Total Attempts: {total}
✅ Success: {success}
❌ Failed: {failed}
📈 Success Rate: {rate:.1f}%

<b>Top 5 Universities:</b>
{top_unis}"""

stats = Stats()

# ============ UTILITIES ============
def random_delay():
    time.sleep(random.randint(MIN_DELAY, MAX_DELAY) / 1000)

def generate_fingerprint() -> str:
    resolutions = ["1920x1080", "1366x768", "1536x864", "1440x900"]
    timezones = [-8, -7, -6, -5, -4]
    languages = ["en-US", "en-GB"]
    platforms = ["Win32", "MacIntel"]

    components = [
        str(int(time.time() * 1000)),
        str(random.random()),
        random.choice(resolutions),
        str(random.choice(timezones)),
        random.choice(languages),
        random.choice(platforms),
        str(random.randint(4, 16)),
    ]
    return hashlib.md5("|".join(components).encode()).hexdigest()

# ============ UNIVERSITY SEARCH ============
def search_universities(query: str) -> List[Dict]:
    try:
        client = httpx.Client(timeout=30)
        params = {"country": "US", "type": "UNIVERSITY", "name": query}
        resp = client.get(ORG_SEARCH_URL, params=params)
        client.close()

        if resp.status_code == 200:
            results = resp.json()
            return results[:15] if isinstance(results, list) else []
        return []
    except Exception as e:
        print(f"Search error: {e}")
        return []

# ============ STUDENT ID CARD GENERATOR ============
def generate_student_id(first: str, last: str, school: str, dob: str) -> bytes:
    """Generate student ID card using external API"""
    try:
        client = httpx.Client(timeout=60)

        # Random template and style for variation
        template = str(random.randint(1, 2))
        style = str(random.randint(1, 6))

        # Generate random student ID
        id_value = f"{random.randint(100, 999)}-{random.randint(100, 999)}-{random.randint(1000, 9999)}"

        payload = {
            "name": f"{first} {last}",
            "university_name": school,
            "dob": dob,
            "academicyear": "2025-2028",
            "template": template,
            "style": style,
            "id_value": id_value,
            "issue_date": time.strftime("%d %b %Y").upper(),
            "exp_date": "31 DEC 2028",
            "issue_txt": "Date Of Issue",
            "exp_txt": "Card Expires",
            "id": "1",
            "opacity": 0.15,
            "principal": "Dr. Academic Dean"
        }

        response = client.post(ID_CARD_API_URL, json=payload)
        client.close()

        if response.status_code == 200:
            print(f"✅ Student ID card generated: {school}")
            return response.content
        else:
            raise Exception(f"API returned status {response.status_code}")

    except Exception as e:
        print(f"❌ Student ID generation error: {e}")
        raise Exception(f"Failed to generate student ID card: {e}")

# ============ VERIFIER ============
class GeminiVerifier:
    def __init__(self, url: str):
        self.url = url
        self.vid = self._parse_id(url)
        self.fingerprint = generate_fingerprint()
        self.client = httpx.Client(timeout=30)
        self.org = None

    def __del__(self):
        if hasattr(self, "client"):
            self.client.close()

    @staticmethod
    def _parse_id(url: str) -> Optional[str]:
        match = re.search(r"verificationId=([a-f0-9]+)", url, re.IGNORECASE)
        return match.group(1) if match else None

    def _request(self, method: str, endpoint: str, body: Dict = None):
        random_delay()
        try:
            headers = {"Content-Type": "application/json"}
            resp = self.client.request(method, f"{SHEERID_API_URL}{endpoint}", json=body, headers=headers)
            try:
                parsed = resp.json() if resp.text else {}
            except:
                parsed = {"_text": resp.text}
            return parsed, resp.status_code
        except Exception as e:
            raise Exception(f"Request failed: {e}")

    def _upload_s3(self, url: str, data: bytes) -> bool:
        try:
            resp = self.client.put(url, content=data, headers={"Content-Type": "image/png"}, timeout=60)
            return 200 <= resp.status_code < 300
        except:
            return False

    def check_link(self) -> Dict:
        if not self.vid:
            return {"valid": False, "error": "Invalid URL"}

        data, status = self._request("GET", f"/verification/{self.vid}")
        if status != 200:
            return {"valid": False, "error": f"HTTP {status}"}

        step = data.get("currentStep", "")
        valid_steps = ["collectStudentPersonalInfo", "docUpload", "sso"]
        if step in valid_steps:
            return {"valid": True, "step": step}
        elif step == "success":
            return {"valid": False, "error": "Already verified"}
        elif step == "pending":
            return {"valid": False, "error": "Already pending review"}
        return {"valid": False, "error": f"Invalid step: {step}"}

    def verify(self, user_data: Dict, org: Dict) -> Dict:
        if not self.vid:
            return {"success": False, "error": "Invalid verification URL"}

        try:
            self.org = org

            check_data, check_status = self._request("GET", f"/verification/{self.vid}")
            current_step = check_data.get("currentStep", "") if check_status == 200 else ""

            if current_step == "collectStudentPersonalInfo":
                body = {
                    "firstName": user_data["firstName"],
                    "lastName": user_data["lastName"],
                    "birthDate": user_data["birthDate"],
                    "email": user_data["email"],
                    "phoneNumber": "",
                    "organization": {"id": org["id"], "idExtended": org["idExtended"], "name": org["name"]},
                    "deviceFingerprintHash": self.fingerprint,
                    "locale": "en-US",
                    "metadata": {
                        "marketConsentValue": False,
                        "verificationId": self.vid,
                        "refererUrl": f"https://services.sheerid.com/verify/{PROGRAM_ID}/?verificationId={self.vid}",
                        "flags": '{"collect-info-step-email-first":"default"}',
                        "submissionOptIn": "By submitting..."
                    }
                }

                data, status = self._request("POST", f"/verification/{self.vid}/step/collectStudentPersonalInfo", body)

                if status != 200:
                    stats.record(org["name"], False)
                    return {"success": False, "error": f"Submit failed: {status}"}

                if data.get("currentStep") == "error":
                    stats.record(org["name"], False)
                    return {"success": False, "error": f"Error: {data.get('errorIds', [])}"}

                current_step = data.get("currentStep", "")

            if current_step == "success":
                stats.record(org["name"], True)
                return {
                    "success": True,
                    "instant": True,
                    "message": "✅ Verified instantly! No document needed.",
                    "document": None
                }

            if current_step == "sso":
                self._request("DELETE", f"/verification/{self.vid}/step/sso")
                check_data, _ = self._request("GET", f"/verification/{self.vid}")
                current_step = check_data.get("currentStep", "")

            if current_step == "docUpload":
                # Generate student ID card
                doc = generate_student_id(
                    user_data["firstName"], 
                    user_data["lastName"], 
                    org["name"], 
                    user_data["birthDate"]
                )

                filename = "student_id.png"

                upload_body = {"files": [{"fileName": filename, "mimeType": "image/png", "fileSize": len(doc)}]}
                data, status = self._request("POST", f"/verification/{self.vid}/step/docUpload", upload_body)

                if not data.get("documents"):
                    stats.record(org["name"], False)
                    return {"success": False, "error": "No upload URL"}

                upload_url = data["documents"][0].get("uploadUrl")
                if not self._upload_s3(upload_url, doc):
                    stats.record(org["name"], False)
                    return {"success": False, "error": "Upload failed"}

                data, status = self._request("POST", f"/verification/{self.vid}/step/completeDocUpload")

                stats.record(org["name"], True)

                return {
                    "success": True,
                    "instant": False,
                    "message": "📄 Document uploaded! Wait 24-48h for manual review.",
                    "document": BytesIO(doc)
                }

            return {
                "success": True, 
                "instant": False, 
                "message": f"✅ Submitted (step: {current_step})",
                "document": None
            }

        except Exception as e:
            if self.org:
                stats.record(self.org["name"], False)
            return {"success": False, "error": str(e)}

# ============ BOT HANDLERS ============
@bot.message_handler(commands=['start'])
def start_command(message):
    user_sessions[message.chat.id] = {}

    text = """🤖 <b>Google One (Gemini) Verification Bot</b>

Bot ini membantu Anda mengisi verifikasi student untuk Google One AI Premium (Gemini) dengan auto-generate Student ID Card.

<b>Cara Pakai:</b>
1. Kirim verification URL dari SheerID
2. Masukkan data mahasiswa (nama, email, dll)
3. Pilih universitas
4. Bot akan generate kartu mahasiswa & proses otomatis

<b>Commands:</b>
/verify - Mulai verifikasi baru
/stats - Lihat statistik (admin only)
/help - Bantuan

<i>✨ Features:</i>
• Auto-generate Student ID Card
• 12 template variations (2 templates × 6 styles)
• Instant verification detection
• Document sent to user & SheerID

<i>Note: US universities only untuk new sign-ups (Jan 2026)</i>"""

    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['help'])
def help_command(message):
    text = """❓ <b>Bantuan</b>

<b>Format URL:</b>
https://services.sheerid.com/verify/...?verificationId=xxx

<b>Data yang diperlukan:</b>
• Nama depan & belakang
• Email (gunakan email sesuai universitas)
• Tanggal lahir (format: YYYY-MM-DD)
• Universitas (pilih dari search)

<b>Tips:</b>
• Gunakan US universities untuk success rate tinggi
• Cari universitas dengan kata kunci spesifik
• Student ID card akan di-generate otomatis
• Dokumen dikirim ke Anda dan ke SheerID

<b>Supported Templates:</b>
• Template 1: Classic red design
• Template 2: Modern shadow design
• 6 color variations each

<b>Developer:</b>
@ThanhNguyxn"""

    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['stats'])
def stats_command(message):
    if ADMIN_IDS and message.chat.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "❌ Admin only command")
        return

    bot.send_message(message.chat.id, stats.get_summary())

@bot.message_handler(commands=['verify'])
def verify_command(message):
    user_sessions[message.chat.id] = {"step": "url"}
    bot.send_message(message.chat.id, "📎 Kirim verification URL dari SheerID:")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    user_id = message.chat.id
    session = user_sessions.get(user_id, {})
    step = session.get("step")

    if not step:
        bot.send_message(user_id, "⚠️ Gunakan /verify untuk mulai")
        return

    if step == "url":
        url = message.text.strip()
        if "sheerid.com" not in url or "verificationId=" not in url:
            bot.send_message(user_id, "❌ URL tidak valid. Harus berisi 'sheerid.com' dan 'verificationId='")
            return

        msg = bot.send_message(user_id, "⏳ Checking URL...")

        verifier = GeminiVerifier(url)
        check = verifier.check_link()

        if not check.get("valid"):
            bot.edit_message_text(f"❌ {check.get('error')}", user_id, msg.message_id)
            user_sessions[user_id] = {}
            return

        bot.edit_message_text(f"✅ URL valid (step: {check.get('step')})", user_id, msg.message_id)

        session["url"] = url
        session["step"] = "first_name"
        bot.send_message(user_id, "👤 Masukkan <b>nama depan</b> (First Name):")

    elif step == "first_name":
        session["firstName"] = message.text.strip()
        session["step"] = "last_name"
        bot.send_message(user_id, "👤 Masukkan <b>nama belakang</b> (Last Name):")

    elif step == "last_name":
        session["lastName"] = message.text.strip()
        session["step"] = "email"
        bot.send_message(user_id, "📧 Masukkan <b>email</b>:")

    elif step == "email":
        email = message.text.strip()
        if "@" not in email:
            bot.send_message(user_id, "❌ Email tidak valid. Coba lagi:")
            return
        session["email"] = email
        session["step"] = "dob"
        bot.send_message(user_id, "🎂 Masukkan <b>tanggal lahir</b> (format: YYYY-MM-DD):\n\nContoh: 2002-05-15")

    elif step == "dob":
        dob = message.text.strip()
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', dob):
            bot.send_message(user_id, "❌ Format tidak valid. Gunakan: YYYY-MM-DD\n\nContoh: 2002-05-15")
            return
        session["birthDate"] = dob
        session["step"] = "uni_search"
        bot.send_message(user_id, "🔍 Cari <b>universitas</b> (min 3 karakter):\n\nContoh: Stanford, MIT, UCLA")

    elif step == "uni_search":
        query = message.text.strip()
        if len(query) < 3:
            bot.send_message(user_id, "❌ Minimal 3 karakter")
            return

        msg = bot.send_message(user_id, f"⏳ Searching '{query}'...")

        results = search_universities(query)

        if not results:
            bot.edit_message_text("❌ Tidak ada hasil. Coba kata kunci lain:", user_id, msg.message_id)
            return

        session["uni_results"] = results

        markup = InlineKeyboardMarkup()
        for idx, uni in enumerate(results[:10]):
            markup.add(InlineKeyboardButton(uni["name"], callback_data=f"uni_{idx}"))
        markup.add(InlineKeyboardButton("🔍 Cari Lagi", callback_data="uni_search_again"))

        bot.edit_message_text(f"📋 Ditemukan {len(results)} universitas:\n\nPilih salah satu:", user_id, msg.message_id, reply_markup=markup)
        session["step"] = "uni_select"

@bot.callback_query_handler(func=lambda call: call.data.startswith("uni_"))
def handle_uni_callback(call):
    user_id = call.message.chat.id
    session = user_sessions.get(user_id, {})

    if call.data == "uni_search_again":
        session["step"] = "uni_search"
        bot.edit_message_text("🔍 Cari universitas (min 3 karakter):", user_id, call.message.message_id)
        return

    try:
        idx = int(call.data.split("_")[1])
        selected_uni = session["uni_results"][idx]

        org = {
            "id": selected_uni["id"],
            "idExtended": str(selected_uni["id"]),
            "name": selected_uni["name"]
        }

        bot.edit_message_text(f"✅ Dipilih: <b>{org['name']}</b>", user_id, call.message.message_id)

        # Start verification
        msg = bot.send_message(user_id, "⏳ <b>Processing verification...</b>\n\n🎨 Generating student ID card...")

        user_data = {
            "firstName": session["firstName"],
            "lastName": session["lastName"],
            "email": session["email"],
            "birthDate": session["birthDate"]
        }

        verifier = GeminiVerifier(session["url"])
        result = verifier.verify(user_data, org)

        if result.get("success"):
            summary = f"""🎉 <b>SUCCESS!</b>

👤 Name: {user_data['firstName']} {user_data['lastName']}
📧 Email: {user_data['email']}
🏫 University: {org['name']}
🎂 DOB: {user_data['birthDate']}

{result.get('message', '')}"""

            bot.edit_message_text(summary, user_id, msg.message_id)

            # Send document to user (both instant and manual review cases)
            if result.get("document"):
                bot.send_document(
                    user_id, 
                    result["document"], 
                    caption="📄 <b>Generated Student ID Card</b>\n\nDocument uploaded to SheerID for verification.",
                    visible_file_name="student_id.png"
                )
            elif result.get("instant"):
                # Instant verification - still send the card to user
                bot.send_message(user_id, "🎊 No document needed - instant verification successful!")
        else:
            bot.edit_message_text(f"❌ <b>FAILED</b>\n\nError: {result.get('error')}", user_id, msg.message_id)

        user_sessions[user_id] = {}

    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")
        user_sessions[user_id] = {}

# ============ RUN BOT ============
if __name__ == "__main__":
    print("🤖 Bot started with Student ID Card Generator integration...")
    print(f"📊 Stats file: {stats.file.absolute()}")
    bot.infinity_polling()

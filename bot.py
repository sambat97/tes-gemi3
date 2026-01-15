"""
Google One (Gemini) Student Verification Bot
Telegram Bot untuk Railway Deployment

Author: ThanhNguyxn
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
from PIL import Image, ImageDraw, ImageFont
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
        return f"📊 <b>Statistics</b>\n\nTotal: {total}\n✅ Success: {success}\n❌ Failed: {failed}\n📈 Rate: {rate:.1f}%"

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

# ============ DOCUMENT GENERATOR ============
def generate_transcript(first: str, last: str, school: str, dob: str) -> bytes:
    w, h = 850, 1100
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    try:
        font_header = ImageFont.truetype("arial.ttf", 32)
        font_title = ImageFont.truetype("arial.ttf", 24)
        font_text = ImageFont.truetype("arial.ttf", 16)
        font_bold = ImageFont.truetype("arialbd.ttf", 16)
    except:
        font_header = font_title = font_text = font_bold = ImageFont.load_default()
    
    draw.text((w//2, 50), school.upper(), fill=(0, 0, 0), font=font_header, anchor="mm")
    draw.text((w//2, 90), "OFFICIAL ACADEMIC TRANSCRIPT", fill=(50, 50, 50), font=font_title, anchor="mm")
    draw.line([(50, 110), (w-50, 110)], fill=(0, 0, 0), width=2)
    
    y = 150
    draw.text((50, y), f"Student Name: {first} {last}", fill=(0, 0, 0), font=font_bold)
    draw.text((w-300, y), f"Student ID: {random.randint(10000000, 99999999)}", fill=(0, 0, 0), font=font_text)
    y += 30
    draw.text((50, y), f"Date of Birth: {dob}", fill=(0, 0, 0), font=font_text)
    draw.text((w-300, y), f"Date Issued: {time.strftime('%Y-%m-%d')}", fill=(0, 0, 0), font=font_text)
    y += 40
    
    draw.rectangle([(50, y), (w-50, y+40)], fill=(240, 240, 240))
    draw.text((w//2, y+20), "CURRENT STATUS: ENROLLED (SPRING 2026)", fill=(0, 100, 0), font=font_bold, anchor="mm")
    y += 70
    
    courses = [
        ("CS 101", "Intro to Computer Science", "4.0", "A"),
        ("MATH 201", "Calculus I", "3.0", "A-"),
        ("ENG 102", "Academic Writing", "3.0", "B+"),
        ("PHYS 150", "Physics for Engineers", "4.0", "A"),
        ("HIST 110", "World History", "3.0", "A")
    ]
    
    draw.text((50, y), "Course Code", font=font_bold, fill=(0,0,0))
    draw.text((200, y), "Course Title", font=font_bold, fill=(0,0,0))
    draw.text((600, y), "Credits", font=font_bold, fill=(0,0,0))
    draw.text((700, y), "Grade", font=font_bold, fill=(0,0,0))
    y += 20
    draw.line([(50, y), (w-50, y)], fill=(0, 0, 0), width=1)
    y += 20
    
    for code, title, cred, grade in courses:
        draw.text((50, y), code, font=font_text, fill=(0,0,0))
        draw.text((200, y), title, font=font_text, fill=(0,0,0))
        draw.text((600, y), cred, font=font_text, fill=(0,0,0))
        draw.text((700, y), grade, font=font_text, fill=(0,0,0))
        y += 30
    
    y += 20
    draw.line([(50, y), (w-50, y)], fill=(0, 0, 0), width=1)
    y += 30
    draw.text((50, y), "Cumulative GPA: 3.85", font=font_bold, fill=(0,0,0))
    draw.text((w-300, y), "Academic Standing: Good", font=font_bold, fill=(0,0,0))
    draw.text((w//2, h-50), "This document is electronically generated and valid without signature.", fill=(100, 100, 100), font=font_text, anchor="mm")
    
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

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
                }
            
            if current_step == "sso":
                self._request("DELETE", f"/verification/{self.vid}/step/sso")
                check_data, _ = self._request("GET", f"/verification/{self.vid}")
                current_step = check_data.get("currentStep", "")
            
            if current_step == "docUpload":
                doc = generate_transcript(user_data["firstName"], user_data["lastName"], org["name"], user_data["birthDate"])
                filename = "transcript.png"
                
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
            
            return {"success": True, "instant": False, "message": f"✅ Submitted (step: {current_step})"}
            
        except Exception as e:
            if self.org:
                stats.record(self.org["name"], False)
            return {"success": False, "error": str(e)}

# ============ BOT HANDLERS ============
@bot.message_handler(commands=['start'])
def start_command(message):
    user_sessions[message.chat.id] = {}
    
    text = """🤖 <b>Google One (Gemini) Verification Bot</b>

Bot ini membantu Anda mengisi verifikasi student untuk Google One AI Premium (Gemini).

<b>Cara Pakai:</b>
1. Kirim verification URL dari SheerID
2. Masukkan data mahasiswa (nama, email, dll)
3. Pilih universitas
4. Bot akan proses otomatis

<b>Commands:</b>
/verify - Mulai verifikasi baru
/stats - Lihat statistik
/help - Bantuan

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
• Dokumen akan di-generate otomatis jika diperlukan

<b>Kontak:</b>
Developer: @ThanhNguyxn"""
    
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
        msg = bot.send_message(user_id, "⏳ <b>Processing verification...</b>")
        
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
            
            # Send document if available
            if result.get("document"):
                bot.send_document(user_id, result["document"], caption="📄 Generated Document")
        else:
            bot.edit_message_text(f"❌ <b>FAILED</b>\n\nError: {result.get('error')}", user_id, msg.message_id)
        
        user_sessions[user_id] = {}
        
    except Exception as e:
        bot.send_message(user_id, f"❌ Error: {str(e)}")
        user_sessions[user_id] = {}

# ============ RUN BOT ============
if __name__ == "__main__":
    print("🤖 Bot started...")
    bot.infinity_polling()

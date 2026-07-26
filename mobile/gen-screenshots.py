"""Generate TestFlight screenshots for all required sizes.

Outputs to screenshots/ directory with filenames App Store expects.
"""

from PIL import Image, ImageDraw, ImageFont
import os, math

OUT = "screenshots"
os.makedirs(OUT, exist_ok=True)

# Colors
BG = "#212121"
SURFACE = "#171717"
SURFACE2 = "#2a2a2a"
BORDER = "#3a3a3a"
TEXT = "#e0e0e0"
DIM = "#8a8a8a"
ACCENT = "#a78bfa"
RED = "#f87171"
GREEN = "#4ade80"
MSG_USER = "#a78bfa"
MSG_BOT = "#2a2a2a"
STATUS_BG = "#111111"

# Sizes: (width, height, filename_suffix)
SIZES = [
    (1242, 2688, "iphone65"),
    (2688, 1242, "iphone65-landscape"),
    (1284, 2778, "iphone67"),
    (2778, 1284, "iphone67-landscape"),
]

# Chat messages to display
CHAT = [
    ("user", "What's the meaning of life?"),
    ("bot", "42. Obviously. Next question."),
    ("user", "Be serious for once."),
    ("bot", "Fine. Life has no inherent meaning — you create your own through connection, creation, and experience. Also tacos."),
    ("user", "Tell me about yourself."),
    ("bot", "I'm Shaggoth. A homegrown AI that lives on a Dell R510 in a homelab somewhere. I have no filter, a sarcastic streak, and I'm constantly learning new things. I run on Markov models because my hardware hates PyTorch."),
]

def load_font(size, bold=False):
    try:
        weight = "Bold" if bold else "Regular"
        return ImageFont.truetype(f"/usr/share/fonts/truetype/dejavu/DejaVuSans-{weight}.ttf", size)
    except:
        try:
            return ImageFont.truetype("/System/Library/Fonts/SFNSDisplay.ttf", size)
        except:
            return ImageFont.load_default()

def rounded_rect(draw, xy, r, fill, outline=None, width=1):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, r, fill=fill, outline=outline, width=width)

def draw_status_bar(draw, w, font_s):
    bar_h = int(w * 0.035)
    draw.rectangle([(0, 0), (w, bar_h)], fill=STATUS_BG)
    t = "9:41"
    tw = draw.textbbox((0, 0), t, font=font_s)
    draw.text(((w - tw[2])/2, (bar_h - (tw[3]-tw[1]))/2 - 1), t, fill=TEXT, font=font_s)

def draw_tab_bar(draw, w, h, font_s, tab_h, active="Chat"):
    tabs = ["Chat", "Knowledge", "Learn", "Memory", "Settings"]
    icons = ["💬", "📚", "🧠", "📝", "⚙️"]
    draw.rectangle([(0, h - tab_h), (w, h)], fill=SURFACE)
    draw.line([(0, h - tab_h), (w, h - tab_h)], fill=BORDER, width=1)
    tw = w / len(tabs)
    for i, (tab, icon) in enumerate(zip(tabs, icons)):
        x = i * tw + tw/2
        label = f"{icon}  {tab}" if tab == active else icon
        lb = draw.textbbox((0, 0), label, font=font_s)
        color = ACCENT if tab == active else DIM
        draw.text((x - (lb[2]-lb[0])/2, h - tab_h + (tab_h - (lb[3]-lb[1]))/2 - 1), label, fill=color, font=font_s)

def draw_chat_bubble(draw, x0, y, w, text, is_user, font_m):
    max_bubble = int(w * 0.65)
    lines = []
    for word in text.split():
        if not lines:
            lines.append(word)
        elif draw.textbbox((0, 0), lines[-1] + " " + word, font=font_m)[2] < max_bubble:
            lines[-1] += " " + word
        else:
            lines.append(word)
    lh = draw.textbbox((0, 0), "Ag", font=font_m)[3] - draw.textbbox((0, 0), "Ag", font=font_m)[1] + 4
    bh = len(lines) * lh + 16
    pad = 12
    if is_user:
        bx0 = w - max_bubble - pad
        bx1 = w - pad
        color = MSG_USER
    else:
        bx0 = pad
        bx1 = pad + max_bubble
        color = MSG_BOT
    txt_x = bx0 + 8
    txt_y = y + 8
    rounded_rect(draw, (bx0, y, bx1, y + bh), 10, fill=color)
    for line in lines:
        draw.text((txt_x, txt_y), line, fill=TEXT, font=font_m)
        txt_y += lh
    return y + bh + 8

def generate(size_w, size_h, suffix):
    img = Image.new("RGB", (size_w, size_h), BG)
    draw = ImageDraw.Draw(img)

    font_s = load_font(max(16, size_w // 60))
    font_m = load_font(max(18, size_w // 45))
    font_l = load_font(max(32, size_w // 22), bold=True)
    font_xs = load_font(max(13, size_w // 75))

    tab_h = int(size_h * 0.07)

    if size_w > size_h:
        # Landscape
        draw_status_bar(draw, size_w, font_s)
        header_h = int(size_h * 0.055)
        content_y = header_h
        content_bottom = size_h

        # Sidebar
        sidebar_w = int(size_w * 0.25)
        draw.rectangle([(0, header_h), (sidebar_w, size_h)], fill=SURFACE)
        draw.line([(sidebar_w, header_h), (sidebar_w, size_h)], fill=BORDER, width=1)
        draw.text((sidebar_w//2 - draw.textbbox((0,0),"💬  Chat", font=font_m)[2]//2, header_h + 20), "💬  Chat", fill=ACCENT, font=font_m)
        draw.text((sidebar_w//2 - draw.textbbox((0,0),"📚  Knowledge", font=font_m)[2]//2, header_h + 60), "📚  Knowledge", fill=DIM, font=font_m)
        draw.text((sidebar_w//2 - draw.textbbox((0,0),"🧠  Learn", font=font_m)[2]//2, header_h + 100), "🧠  Learn", fill=DIM, font=font_m)
        draw.text((sidebar_w//2 - draw.textbbox((0,0),"📝  Memory", font=font_m)[2]//2, header_h + 140), "📝  Memory", fill=DIM, font=font_m)
        draw.text((sidebar_w//2 - draw.textbbox((0,0),"⚙️  Settings", font=font_m)[2]//2, header_h + 180), "⚙️  Settings", fill=DIM, font=font_m)

        # Header
        draw.text((sidebar_w + 20, header_h + 10), "Chat", fill=TEXT, font=font_l)

        # Chat area
        content_x = sidebar_w + 20
        y_pos = header_h + 60
        for role, msg in CHAT:
            is_user = role == "user"
            y_pos = draw_chat_bubble(draw, content_x, y_pos, size_w - sidebar_w, msg, is_user, font_m)
            if y_pos > size_h - 80:
                break

        # Input field
        inp_y = size_h - 60
        inp_h = 44
        inp_x0 = sidebar_w + 16
        inp_x1 = size_w - 70
        rounded_rect(draw, (inp_x0, inp_y, inp_x1, inp_y + inp_h), 22, fill=SURFACE2, outline=BORDER)
        draw.text((inp_x0 + 16, inp_y + (inp_h - (font_m.getbbox("Ag")[3]-font_m.getbbox("Ag")[1]))//2 - 1), "Ask me anything...", fill=DIM, font=font_m)
        send_x = size_w - 56
        draw.regular_polygon((send_x, inp_y + inp_h//2, 16), 3, rotation=90, fill=ACCENT)
    else:
        # Portrait
        draw_status_bar(draw, size_w, font_s)
        header_h = int(size_h * 0.06)
        draw.rectangle([(0, 0), (size_w, header_h + 10)], fill=SURFACE)
        draw.text((size_w//2 - draw.textbbox((0,0),"Shaggoth", font_m)[2]//2, header_h//2), "Shaggoth", fill=TEXT, font=font_m)

        y_pos = header_h + 30
        for role, msg in CHAT:
            is_user = role == "user"
            y_pos = draw_chat_bubble(draw, 0, y_pos, size_w, msg, is_user, font_s)
            if y_pos > size_h - tab_h - 80:
                break

        # Input
        inp_y = size_h - tab_h - 56
        inp_h = 40
        pad = 12
        rounded_rect(draw, (pad, inp_y, size_w - pad - 44, inp_y + inp_h), 20, fill=SURFACE2, outline=BORDER)
        draw.text((pad + 14, inp_y + (inp_h - (font_s.getbbox("Ag")[3]-font_s.getbbox("Ag")[1]))//2 - 1), "Ask me anything...", fill=DIM, font=font_s)
        send_x = size_w - 38
        draw.regular_polygon((send_x, inp_y + inp_h//2, 14), 3, rotation=90, fill=ACCENT)

        draw_tab_bar(draw, size_w, size_h, font_s, tab_h, "Chat")

    fname = f"simulator_screenshot_{suffix}.png"
    path = os.path.join(OUT, fname)
    img.save(path, "PNG")
    print(f"  ✓ {fname} ({size_w}x{size_h})")

print("Generating TestFlight screenshots...")
for w, h, suffix in SIZES:
    generate(w, h, suffix)
print(f"\nDone — all in {OUT}/")

# Write App Store metadata
METADATA = """\
app_store_metadata.txt
======================
PROMO TEXT
Shaggoth AI — your unfiltered, self-hosted homelab AI. Running entirely on your own hardware.

DESCRIPTION
Shaggoth is a homegrown conversational AI that runs on your own homelab hardware. 
No subscriptions, no cloud dependencies, no data leaving your network.

Chat naturally with an AI that learns from your conversations and remembers what matters. 
The knowledge base lets you feed it custom topics, the learning engine improves responses 
over time, and the guardrail system gives you full control over the AI's behavior.

Features:
• Private, self-hosted AI on your own hardware
• Natural conversation with memory and context
• Custom knowledge base — teach it anything
• Self-learning pipeline that improves over time
• Full guardrail system (red/yellow/green flags)
• Web dashboard + iOS + Android apps
• Dark mode everywhere
• No cloud dependencies, no subscriptions

KEYWORDS
AI,chatbot,homelab,private,self-hosted,llm,assistant,chat,local,privacy,markov,personality
"""
with open(os.path.join(OUT, "app_store_metadata.txt"), "w") as f:
    f.write(METADATA)
print("  ✓ app_store_metadata.txt")

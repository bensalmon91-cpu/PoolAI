# PoolAIssistant Quick Start Guide

**Simple instructions to get you up and running!**

---

## 🎯 What You Need to Know

PoolAIssistant is a Raspberry Pi that monitors your pool controllers and displays the data on a webpage.

---

## 🌐 Accessing the Dashboard

### Method 1: The Easy Way (Recommended)

1. **Make sure** your computer/phone is on the **same network** as the Pi
2. **Open** any web browser
3. **Type** this in the address bar:
   ```
   http://poolai.local:8080
   ```
4. Press **Enter**

**That's it!** You should see your pool dashboard.

---

### Method 2: Using the Access Point (If Easy Way Doesn't Work)

The Pi creates its own WiFi network for 30 minutes when it boots up.

#### Step-by-Step:

1. **On your phone/laptop:**
   - Open WiFi settings
   - Look for: **PoolAIssistant**
   - Connect using password: `12345678`

2. **Open your browser:**
   - Go to: `http://192.168.4.1:8080`

3. **Connect to your WiFi:**
   - Click **Settings** tab
   - Scroll to "Network" section
   - Enter your WiFi name and password
   - Click **Save Wi-Fi settings**

4. **Reconnect to your regular WiFi**
   - The Pi will now be on your network
   - Access it using Method 1 above

---

## 📊 What You'll See

Once connected, you'll see:

- **Pool Tabs** - One for each pool (Main, Vitality, Spa, Plunge)
- **Settings** - Configure controllers and WiFi
- **Alarms** - View any active warnings or errors (click pool name → Alarms)

### The Vertical Alarm Banner

If you see an **orange or red bar** on the right side:
- 🟠 **Orange** = Warning (attention needed soon)
- 🔴 **Red** = Critical (immediate attention)
- Click the **×** at the top to dismiss temporarily

---

## 🔧 Common Tasks

### Viewing Controller Data
1. Click any **pool tab** at the top
2. Scroll to see live readings (chlorine, pH, temperature, etc.)
3. Click graphs to see history

### Checking Alarms
1. Click a **pool tab**
2. Click the **Alarms** link (if visible)
3. See active alarms and what action to take

### Changing WiFi Settings
1. Click **Settings** tab
2. Find "Network" section
3. Enter new WiFi name and password
4. Click **Save Wi-Fi settings**

### Accessing Controller Interfaces
1. Click **Settings** tab
2. Scroll to **Controller Web Access**
3. Click **Open Controller →** for any controller
4. Controller opens in new tab

---

## 🆘 Troubleshooting

### "Can't connect to poolai.local"

**Try these in order:**

1. **Check you're on the same network** as the Pi
2. **Try the IP address instead:**
   - Find the Pi's IP on your router (usually something like `10.0.30.80`)
   - Use: `http://10.0.30.80:8080` (replace with actual IP)
3. **Use the Access Point method** (see Method 2 above)

### "The page is loading very slowly"

- **Normal on first load** (database is large)
- Settings page: < 1 second
- Charts: 1-6 seconds
- If longer than 10 seconds, refresh the page

### "I forgot the WiFi password"

Don't worry! The Pi broadcasts its Access Point when not connected:
1. Wait for Pi to be on for 30+ minutes without WiFi
2. AP will turn on automatically
3. Connect to "PoolAIssistant" WiFi (password: `12345678`)
4. Reconfigure network settings

---

## 📱 Quick Reference

| Task | Address |
|------|---------|
| **View Dashboard** | `http://poolai.local:8080` |
| **Access Point WiFi** | Network: `PoolAIssistant` |
| **AP Password** | `12345678` |
| **AP Dashboard** | `http://192.168.4.1:8080` |

---

## 🔐 Advanced: SSH Access

For system administrators only:

**Connect:**
```bash
ssh poolai@poolai.local
```

**Common Commands:**
```bash
# Check if services are running
sudo systemctl status poolaissistant_logger
sudo systemctl status poolaissistant_ui

# View logs
journalctl -u poolaissistant_logger -f

# Reboot Pi
sudo reboot
```

---

## 💡 Tips

- **Bookmark the dashboard** in your browser for quick access
- **Mobile friendly** - works great on phones and tablets
- **24/7 monitoring** - Pi runs continuously, logging data
- **Access Point** always available as fallback if WiFi fails

---

## 🆘 Need Help?

1. Check the full **README.md** for detailed documentation
2. View **ALARM_IMPROVEMENTS.md** for alarm explanations
3. Check **DEPLOYMENT_GUIDE.md** for advanced setup

---

**Version:** PoolAIssistant v6.1.1
**Last Updated:** January 2026

---

*Happy Monitoring! 🏊*

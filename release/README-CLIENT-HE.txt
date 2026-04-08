Avivi Client — התקנה ללקוחות (ZIP + הפעלה אוטומטית)
===================================================

מה יש בחבילה
------------
התיקייה release מכילה:
- AviviClient.zip            (האפליקציה ללקוח)
- install.ps1               (התקנה + הפעלה אוטומטית ב-Startup)
- update.ps1                (עדכון לפי ZIP+SHA256)
- run.ps1                   (Startup: עדכון ואז הפעלת האפליקציה)
- uninstall.ps1             (הסרה)

התקנה (מומלץ)
-------------
1) חלץ את AviviClient.zip (או השאר ליד install.ps1)
2) פתח PowerShell והרץ:

  powershell -ExecutionPolicy Bypass -File .\install.ps1 -MasterUrl http://IP-של-המאסטר:8000

עם עדכון אוטומטי ב-Startup (מומלץ)
---------------------------------
כדי שהלקוח יעדכן את עצמו בכל הפעלה, צריך URL קבוע ל-2 קבצים:
  1) AviviClient.zip
  2) AviviClient.sha256  (שורה ראשונה: SHA256 של ה-ZIP)

ואז להתקין עם:

  powershell -ExecutionPolicy Bypass -File .\install.ps1 `
    -MasterUrl http://IP-של-המאסטר:8000 `
    -UpdateZipUrl  https://YOURDOMAIN/AviviClient.zip `
    -UpdateSha256Url https://YOURDOMAIN/AviviClient.sha256

אופציונלי:
  -DesktopShortcut            יוצר קיצור דרך על שולחן העבודה
  -OwnerTelegramToken         טוקן לבוט "בעלים" (אם משתמשים)
  -OwnerTelegramChatId        Chat ID מורשה לבוט הבעלים

דוגמה:
  powershell -ExecutionPolicy Bypass -File .\install.ps1 `
    -MasterUrl http://192.168.1.10:8000 `
    -DesktopShortcut

איפה זה מותקן?
--------------
- קבצי אפליקציה: %LOCALAPPDATA%\Avivi\ClientApp\
- קיצור דרך Startup: %APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\AviviClient.lnk
- הגדרות סוכן: %LOCALAPPDATA%\Avivi\client_settings.json
- הגדרות עדכון: %LOCALAPPDATA%\Avivi\update_config.json

שימוש אחרי התקנה
---------------
- הפעל את AviviClient.exe (אמור להיפתח UI)
- הגדר Master URL אם צריך ולחץ "Enroll with Master"
- אחרי Enroll, הסוכן שולח heartbeat והמאסטר מציג אותו בדשבורד

הסרה
-----
  powershell -ExecutionPolicy Bypass -File .\uninstall.ps1

הסרה מלאה כולל נתונים (כולל credentials/missions):
  powershell -ExecutionPolicy Bypass -File .\uninstall.ps1 -PurgeData

Troubleshooting
---------------
1) הדשבורד ריק:
   - ודא שהמאסטר רץ (http://127.0.0.1:8000/health)
   - ודא שעשית Enroll בלקוח

2) "Access denied" בהרצה:
   - נסה להריץ את PowerShell כמשתמש רגיל (התקנה ל-LOCALAPPDATA לא דורשת Admin)
   - בדוק Antivirus/Defender שחוסם

3) הלקוח לא מצליח להתחבר למאסטר:
   - בדוק firewall/רשת ופורט 8000
   - נסה לפתוח בדפדפן מהמחשב של הלקוח: http://IP-של-המאסטר:8000/health

4) עדכון אוטומטי לא עובד:
   - ודא ש-UpdateZipUrl ו-UpdateSha256Url עובדים בדפדפן
   - ודא שקיים קובץ AviviClient.sha256 תקין (SHA256 של ה-ZIP)
   - אם יש Proxy/Firewall שמונע הורדה – צריך לאפשר לכתובת ה-HTTPS

איך מייצרים AviviClient.sha256 (בשרת העדכונים)
----------------------------------------------
ב-Windows:
  certutil -hashfile AviviClient.zip SHA256 > AviviClient.sha256

הקובץ יכול להכיל גם שם קובץ; הסקריפט קורא את הטוקן הראשון (ה-Hash).


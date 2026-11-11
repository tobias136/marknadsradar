# Marknadsradar som Android-app (APK)

Det här är ett Android-projekt som packar hela Marknadsradar i en app. Python, pandas och webbservern ligger inne i appen och körs på telefonen. Din journal, dina portföljer och dina listor ligger kvar på telefonen.

**Kursdata från Yahoo:** yfinance fungerar inte på Android, så appen använder en egen Yahoo-klient (`app/yahoo_http.py`) som gör anropen med telefonens egen nätverksstack (cookie, crumb och EU-samtycke hanteras). Samma Python-kod körs på datorn med yfinance som förut.

> **Läs det här först.** Projektet är skrivet utan tillgång till Android SDK och utan tillgång till Yahoo, så det är **inte byggt eller provkört på en telefon**. Tolkningen av Yahoos svar är testad mot en simulerad Yahoo, inte mot riktiga svar. Räkna med att första bygget kan kräva en liten justering (se *Om bygget misslyckas*) och att Yahoo kan ändra sig.

## Bygg APK utan att installera något på datorn (GitHub)
1. Skapa ett **privat** repo på github.com och ladda upp hela mappen `marknadsradar` (så att `android-app/` och `.github/` ligger i repots rot).
2. Gå till fliken **Actions**, välj **Bygg Android-APK** och tryck **Run workflow**. Bygget tar cirka 10–20 minuter.
3. När det är klart: öppna körningen och ladda ner **Marknadsradar-apk** längst ner. Packa upp zip-filen, du får `app-debug.apk`.

## Bygg i Android Studio
1. Installera Android Studio och öppna mappen `android-app`.
2. Låt Gradle synka (kräver internet) och välj **Build → Build APK(s)**.
3. APK:n hamnar i `android-app/app/build/outputs/apk/debug/app-debug.apk`.

## Installera på telefonen
1. Skicka APK-filen till telefonen (mejl, Drive, USB).
2. Öppna filen. Android frågar om du tillåter installation från den appen (Chrome, Filer, …). Tillåt det.
3. Första starten tar en stund (10–30 sekunder) eftersom Python och pandas startar. Därefter öppnas Marknadsradar.
4. Nya versioner kan installeras direkt över den gamla, så din data finns kvar. Det fungerar bara om alla bygge signeras med samma nyckel. Nyckeln ligger som hemligheter i GitHub (`MR_KEYSTORE_BASE64`, `MR_KEYSTORE_PASSWORD`, `MR_KEY_ALIAS`, `MR_KEY_PASSWORD`) och aldrig i repot. Utan dem får varje bygge en ny tillfällig nyckel. Avinstallerar du appen raderas datan, så ta en säkerhetskopia först (Claude-export eller exportfunktionerna i appen).

## Hur det hänger ihop
- `MainActivity.kt` startar Python (Chaquopy), startar servern på `127.0.0.1:8765` och visar den i en WebView. Servern kräver en slumpad nyckel som bara appen känner till, så andra appar på telefonen kommer inte åt dina data.
- `YahooHttp.kt` gör Yahoo-anropen åt Python.
- `app/build.gradle.kts` kopierar programkoden från projektets rot inför varje bygge, så det finns bara en version av koden.
- Appen använder FastAPI 0.99 med pydantic 1 på Android, eftersom pydantic 2 kräver ett kompilerat paket som saknas för Android. På datorn fungerar både 1 och 2.

## Begränsningar
- Kurser och bolagsdata uppdateras bara medan appen är öppen. Android stänger appar i bakgrunden, så den automatiska uppdateringen går inte när appen inte körs.
- Yahoo kan neka anrop (429) eller ändra sina gränssnitt. Då visar appen ett felmeddelande vid uppdatering. Historik som redan hämtats finns kvar.
- APK:n är stor (cirka 100–150 MB) eftersom den innehåller Python, numpy och pandas.
- Installationen är för personligt bruk. Den är inte signerad för Google Play.

## Om bygget misslyckas
| Felmeddelande (ungefär) | Åtgärd |
|---|---|
| `No matching distribution found for pandas` (eller numpy) | Chaquopys paketindex saknar den versionen för vald Python. I `app/build.gradle.kts`: ändra `version = "3.12"` till `"3.11"`, eller fäst en version, till exempel `install("pandas==2.2.2")`. |
| `Could not find com.chaquo.python:gradle` | Kontrollera att `google()` och `mavenCentral()` finns i `settings.gradle.kts` och att bygget har internet. |
| `Unsupported class file major version` | Bygg med Java 17 (Android Studio: Settings → Build Tools → Gradle → Gradle JDK = 17). |
| Appen visar "Servern startade inte" och en logg | Skicka loggen till mig. Där står oftast ett Python-fel, till exempel ett paket som saknas. |
| Kursdata uppdateras inte | Öppna Inställningar/uppdatera och läs felet. `429` betyder att Yahoo begränsar anrop, vänta en stund. |

Loggar från telefonen: anslut via USB och kör `adb logcat | grep -i python`.

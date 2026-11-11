# Marknadsradar på Android

> Vill du ha en riktig APK-fil i stället för Termux? Se `../android-app/README.md`.

Det finns två sätt. Båda ger samma app, och du kan lägga den som en ikon på startskärmen.

## A. Kör på mobilen (Termux)
Allt ligger på telefonen, inklusive din journal och dina portföljer.

1. Installera **Termux** från F-Droid (Play-versionen är gammal och fungerar inte).
2. Lägg mappen `marknadsradar` på telefonen, till exempel i Termux hemmapp. Packa upp zip-filen med `unzip marknadsradar.zip`.
3. I Termux: `cd marknadsradar && bash android/termux-setup.sh`. Det tar några minuter. Skriptet avslutas med en kontroll som visar vilka paket som fungerar.
4. Starta med `bash android/start.sh`. Chrome öppnas på `http://localhost:8000`. Prova först med `bash android/start.sh --demo` om du vill se att allt fungerar.
5. I Chrome: menyn **⋮ → Lägg till på startskärmen → Installera**. Appen öppnas då i helskärm. Själva servern måste ändå startas i Termux först.

Tips: tillåt Termux att köra i bakgrunden och stäng av batterioptimering för Termux, annars kan Android stänga servern.

**Osäkert:** kursdata hämtas med yfinance, som i nya versioner kräver ett paket (`curl_cffi`) som kan vara svårt att installera på Android. Skriptet provar en variant utan det, men Yahoo kan då neka anrop. Kontrollen i slutet av installationen visar bara att paketet går att importera. Om kursuppdateringen misslyckas, använd alternativ B.

## B. Kör på datorn, öppna på mobilen
Datorn gör jobbet och mobilen är bara skärmen. Fungerar bäst om du redan använder appen på datorn.

1. På datorn: `python run.py --lan`
2. Programmet skriver en adress med åtkomstnyckel, till exempel `http://192.168.1.20:8000/?key=…`. Öppna den i Chrome på mobilen (samma wifi).
3. Nyckeln sparas i webbläsaren efter första besöket. Dela den inte, den ger full åtkomst till din journal och dina portföljer. Starta om programmet för en ny nyckel, eller ange egen med `--key`.
4. Menyn **⋮ → Lägg till på startskärmen** skapar en genväg. Full installation som app (och offlineskal) kräver HTTPS eller localhost, så det fungerar bara i alternativ A.

Datorn måste vara på och programmet igång. Åtkomst utanför hemmanätet kräver en säker tunnel, till exempel Tailscale. Öppna aldrig porten mot internet.

## Säkerhetskopia
All data ligger i mappen `data/`. Kopiera den för att flytta eller säkerhetskopiera.

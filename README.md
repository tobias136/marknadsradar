# Marknadsradar

Lokal app för att bevaka marknaden sektor för sektor: egna bevakningslistor, värmekarta över sektorrotation, jämförelsediagram, nyckeltal per aktie, kvartalsrapportsammanfattningar och en export som Claude kan läsa för att analysera marknadsläget.

Allt körs på din dator. Inget konto behövs och appen lyssnar bara på `127.0.0.1` (ingen annan på nätverket kommer åt den).

## Kom igång

Kräver Python 3.10 eller nyare.

```bash
cd marknadsradar
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run.py
```

Webbläsaren öppnas på http://127.0.0.1:8000. Första starten hämtar två års kurshistorik och bolagsdata för alla förvalda listor (någon minut). Därefter uppdateras det automatiskt.

Vill du bara titta på gränssnittet utan nätverk: `python run.py --demo`. Då används påhittad data (tydligt märkt med en gul banderoll) och en separat databas, så den blandas aldrig med din riktiga.

## Vad du kan göra

| Flik | Innehåll |
|---|---|
| **Översikt** | Nyckelkort (marknadsbredd, starkaste/svagaste grupp, index, signalläge), värmekarta per sektor/tema över 1d–1 år med relativ styrka mot ditt index, rangordningsdiagram, sorterbar tabell med RSI, avstånd till 200-dagars, 52-veckorshögsta, P/E, signalbetyg, nästa rapportdatum och trendgraf. |
| **Jämför** | Valfria värdepapper i listan indexerade till 100, absolut eller relativt index. Perioder 1 mån–2 år. |
| **Rapporter** | Senaste kvartalet per bolag: omsättning, tillväxt, marginaler, nettoresultat, EPS mot förväntan, kommande rapportdatum. Klicka på en rad för en löpande sammanfattning. |
| **Aktie** | **Signalbetyg** med förklaring pelare för pelare, kursgraf med SMA50/SMA200 och volym, avkastning, risk, tekniska indikatorer (MACD, ADX, ATR-stopp m.fl.), värdering, lönsamhet, kvartalsgraf, tabell över kvartal, EPS-överraskningar och egna anteckningar. |
| **Makro** | Marknadens "väder": VIX, räntor och räntekurva, kreditoro, dollar, USD/SEK, olja, guld, koppar och en enkel regim (risk-on/blandat/risk-off) med skälen. |
| **Portfölj** | Innehav manuellt eller via Avanza-CSV, värde i kronor, vikter, koncentration, effektivt antal innehav, sektor- och valutafördelning, svängning, beta, korrelationer, varningar och positionsstorlekskalkylator. |
| **Journal** | Logga beslut med tes och "jag ändrar mig om …" medan utgången är okänd, granska senare och se din egen statistik. |
| **Backtest** | Testar den tekniska delen av signalbetyget mot historiken: vad hände efter positiva/negativa betyg jämfört med alla dagar, enkel strategi mot att bara äga, och tydliga förbehåll. |
| **Claude-export** | Hela marknadsläget (inklusive makro, portfölj, journal och backtest) som Markdown/JSON, med förslag på fråga till Claude. |
| **Ordlista** | Närmare 100 begrepp förklarade för lekmän, med exempel och hur man läser siffran. Ett fåtal är märkta som planerade. |
| **Karriär** | Valfritt spelläge: 7 nivåer med uppdrag och quiz. Se nedan. |

### Förklaringar för nybörjare
- Nästan varje rubrik, förkortning och kolumn har en liten **?**-ikon. Håll muspekaren över den för en snabb förklaring, klicka för hela förklaringen med exempel.
- Varje flik har en hopfällbar ruta **💡 Så läser du den här sidan** med en steg-för-steg-guide.
- Ikonerna kan stängas av under ⚙ Inställningar.

### Spelläge (Karriär)
Ett frivilligt tillägg som gör inlärningen till nivåer: Nybörjare, Kartläsare, Trendspanare, Analytiker, Riskhanterare, Strateg och Förvaltare. Varje nivå har uppdrag (läsa, använda funktioner, skriva journal, granska) och ett quiz på fem frågor (minst fyra rätt). Poäng ges aldrig för antal affärer och aldrig för vinst på enskilda beslut. De sista uppdragen kräver stora urval (till exempel 20 granskade beslut) så att tur inte belönas. Allt räknas ur dina egna data. Stäng av under ⚙ Inställningar: då döljs fliken och inget loggas.

### Öva (övningar)
Fliken **Öva** har sex övningar som skapas av appens egen kursdata (namn och datum är dolda tills du svarat) och rättas på servern:
- **Läs diagrammet:** medelvärden (SMA50/200), största nedgång, RSI-zon, vilken aktie som svänger mest, nära 52-veckorstoppen och slog aktien indexet.
- **Riskräknaren:** positionsstorlek från risk och stopp, andel av portföljen, hur mycket en aktie måste stiga efter ett fall, R-multipel, positionsgräns och förväntat värde. Nya tal varje gång.
- **Hitta felet:** fiktiva portföljer med en koncentration, branschrisk, valutarisk, överlapp, för många små innehav, eller inget allvarligt fel.
- **Stoppövning:** du placerar stoppet själv och ser vad som hände de följande 60 dagarna. Bedömningen gäller hur långt stoppet ligger från dagsbruset (ATR), inte utfallet.
- **Stoppsimulator:** jämför inget stopp, fasta, släpande, ATR- och tidsstopp på hundratals historiska affärer i en vald aktie, med andel utlösta, utskakade, sämsta 10 % och gap. Utlöses på dagens lägsta kurs; öppnar kursen under stoppet fylls du till öppningskursen.
- **Repetitionskort:** begreppen i Ordlistan med växande mellanrum (1, 3, 7, 16, 35, 90 dagar). Missade kort kommer tillbaka direkt.

### Övningsportfölj (pappershandel)
Fliken **Övningsportfölj** låter dig handla med virtuella pengar till riktiga kurser, i flera portföljer med olika strategier som du kan jämföra. Varje köp kräver tes (minst 30 tecken), vad som skulle visa att du har fel, stoppkurs och antal. Köp sker till senaste stängningskurs, courtage 0,1 % per affär ingår, och utländska kurser räknas om till kronor. Stoppen tillämpas automatiskt när kurserna uppdateras och kan bara höjas, aldrig sänkas. Varje stängd affär ger upp till 100 **processpoäng**: 20 för komplett plan, 30 för risk högst 2 % av portföljen, 20 för position högst 25 % och 30 för granskning med lärdom. Vinst ger inga poäng. Pappershandel saknar känslorna, så den lär ut process men inte hur det känns med riktiga pengar. Portföljerna ingår i Claude-exporten.

### Handlarens verktyg (under Öva)
**Beteendefällor** är korta scenarier där du pekar ut tankevurpan (förlustaversion, FOMO, bekräftelsebias m.fl.) och får ett motmedel. **Spelboken** är dina skriftliga regler i sex avsnitt plus egna gränser för risk och nedgång. **Månadsgranskningen** hämtar siffror ur övningsportföljen och låter dig skriva vad som gick bra, sämre och vad du ändrar (kräver minst tre stängda övningsaffärer under månaden). Spelbok och granskningar ingår i Claude-exporten.

#### Nivå 8–10: Riskchef, Systematiker, Handlare
- **Stresstest** (övning) och **Riskpanel** (verktyg): räkna på marknadsfall, gap genom stoppen och risktak, och stresstesta egna övningsportföljer mot gränserna i Spelboken (öppen risk och nedgång). Riskpanelen visar också om du hållit gränserna i 60 handelsdagar.
- **Tur eller skicklighet** (övning) lär ut hur mycket slumpen ger, med exakta sannolikheter för vinstserier och längsta förlustserier.
- **Handelsstatistik:** snitt i R (expectancy), träffandel, vinst/förlust-kvot, längsta förlustserie, största nedgång i R, alltid med 95 %-intervall (bootstrap och Wilson), samt jämförelse av två portföljer med skillnadsintervall.
- **Regeltest:** skriv hypotes, välj villkor (trend, pullback, RSI, utbrott, relativ styrka med mera), stopp i ATR och tid. Köp nästa dags öppning, ingen överlappning per aktie. Resultatet jämförs mot samma stopp och tid på alla dagar, delas i två halvor och räknar hur många regler du redan provat.
- **Handlarprofil:** statistik, process, risk, Spelbok, lärdomar och ett ärligt utlåtande (för tidigt / ingen påvisbar fördel / förenligt med fördel / talar emot) utifrån intervallet för snitt-R. Märks *Visad professionell process* när alla krav är uppfyllda: 50 affärer över minst sex månader, processsnitt över 80, Spelbok, sex månadsgranskningar, hållna riskgränser och ett skrivet beslut. Inget av kraven är avkastning.
- Nivå 8–10 är tidsgrindade av design. Statistik och profil ingår i Claude-exporten.

### Signalbetyg (−100 till +100)
Betyget sammanfattar fem pelare: trend, momentum, relativ styrka mot index, rapporter (lönsamhet och tillväxt) samt värdering. Varje pelare får −2 till +2 efter öppna regler som visas i klartext på aktiesidan, tillsammans med varningar och en nivå som skulle ändra bilden. Betyget är **regelbaserat och inte backtestat**, och det är inte ett köp- eller säljråd.

### Egna listor
- **+ Ny lista** i sidomenyn: ge den ett namn, ett jämförelseindex (t.ex. `SPY`, `^OMX`, `^GSPC`) och klistra in tickers.
- Nya bolag grupperas automatiskt per sektor. Klicka på en grupp i tabellen för att döpa om den, så kan du bygga egna teman.
- **Tickers** är Yahoo Finance-symboler. Svenska aktier har suffixet `.ST` (`VOLV-B.ST`, `ERIC-B.ST`), amerikanska är vanliga (`AAPL`). Förvalda tickers kan behöva justeras om ett bolag byter symbol.

### Uppdateringsintervall
⚙ Inställningar → välj Av / 5 min / 15 min / 30 min / varje timme / var 2:a / var 4:e timme / varje dygn. Appen måste vara igång för att uppdatera. För sektorrotation räcker en gång per dag efter börsstängning; gratisdata är oftast fördröjd cirka 15 minuter.

## Samband mellan bolag

Fliken **Samband** undersöker om ett bolags rörelser följs av andra bolags rörelser, och samlar relationer (leverantör, ägande, samarbete) med källa.

- **Lead-lag:** alla par i dina listor, 1–5 dagars fördröjning, rensat från marknaden. P-värdena korrigeras för antalet tester (Benjamini–Hochberg, FDR 10 %), och varje resultat visar om samma riktning finns i båda halvorna av perioden. På slumpdata hittas nästan inget, medan ett inlagt samband upptäcks.
- **Händelser:** hur andra bolag rör sig kring ett bolags rapporter eller kraftiga rörelser (omslumpnings-p och bootstrap-intervall, händelser närmare än 6 dagar slås ihop).
- **Relationer:** egna inlägg med typ, styrka och obligatorisk källlänk. Täckningen visar vilka bolag som gåtts igenom. Import av många via JSON.
- **Automatisk uppdatering:** varje vecka söker appen efter ägande-, dotter- och moderbolagsrelationer mellan bolag i dina listor (Wikidata), kontrollerar att källänkarna svarar och flaggar relationer äldre än 18 månader. Fynd hamnar i en inkorg och blir relationer först när du godkänner. Leverantörs- och kundrelationer går inte att hämta strukturerat och läggs in manuellt eller via import. Kräver internet; körs inte i demoläge, men knappen Kör nu finns alltid.
- Aktiesidan visar bolagets relationer och lead-lag, Övningsportföljens köpdialog varnar för överlapp med öppna innehav, Claude-exporten tar med resultaten, och övningen **Samband eller slump** visar varför man måste korrigera.
- Begränsningar: rapportdatum saknar klockslag, bolag på olika börser stänger vid olika tider, och historiska samband behöver inte hålla framåt. Allt är beskrivande statistik, inget köpråd.

## Android

Appen går att använda på mobilen på två sätt: köra den i Termux på telefonen, eller köra den på datorn med `python run.py --lan` och öppna den på mobilen. Båda kan läggas på startskärmen. Se `android/README_ANDROID.md`. Layouten är anpassad för smala skärmar.

Det finns också ett Android-projekt som bygger en riktig APK med Python inbyggt och egen Yahoo-klient: se `android-app/README.md`. Det bygger du med Android Studio eller med GitHub Actions (`.github/workflows/android.yml`).

## Låt Claude analysera marknadsläget

Efter varje uppdatering skrivs två filer:

- `data/export/snapshot.md`: läsbar sammanställning (grupper, signaler, alla värdepapper, kvartalssammanfattningar, kommande rapporter, dina anteckningar)
- `data/export/snapshot.json`: samma data strukturerat

Du kan också hämta dem live: `http://127.0.0.1:8000/api/snapshot.md` och `/api/snapshot`.

Ladda upp filen i ett Claude-samtal (eller i ditt projekt) och be om en analys. Fliken Claude-export har en färdig fråga. Körs Claude lokalt (t.ex. Claude Code) kan den läsa filerna i `data/export/` direkt.

## Portfölj och Avanza-import
Appen känner inte till Yahoo-tickers för det du äger. Därför läser importen Avanzas transaktionsexport (semikolonseparerad CSV med Köp/Sälj), räknar fram nuvarande antal och snittpris, och du kopplar sedan varje innehav till en Yahoo-ticker (appen föreslår tickers från dina bevakningslistor). Importparsern är skriven efter Avanzas vanliga kolumnnamn men är **inte testad mot en riktig Avanza-fil**. Kontrollera antal och namn mot Avanza efter importen. Courtage, utdelningar och valutaeffekter ingår inte i snittpriset. Du kan också lägga in innehav för hand.

## Backtest: vad den kan och inte kan
Testet gäller bara trend, momentum och relativ styrka (fundamenta och värdering finns inte historiskt i gratisdatan). Det visar om betyget hade samband med vad som hände efteråt, inte om det kommer fungera framåt. Urvalet är dagens bolag (survivorship bias), mätfönstren överlappar och historiken är högst fem år. Appen hämtar nu 5 års kurshistorik; tryck Uppdatera efter uppgraderingen så fylls den på.

## Så ska siffrorna läsas
- Avkastning är i procent, i varje värdepappers egen valuta (ingen valutaomräkning), justerad för utdelningar och splittar.
- Perioder räknas som kalenderperioder bakåt från senaste kursdatum (1v = 7 dagar, 1m, 3m, 6m och 1 år = lika många månader/år bakåt), med sista stängningen på eller före datumet som jämförelsekurs. Håll muspekaren över en siffra för att se jämförelsedag och startkurs. “I år” räknas från sista stängningen föregående år. Indikatorer som SMA, RSI och backtestet räknar fortfarande i handelsdagar.
- Gruppavkastning är ett likaviktat medelvärde. En grupp med ett enda värdepapper visar bara det.
- Relativ styrka = avkastning minus indexets, i procentenheter.
- Marknadsbredd = andel av listans värdepapper som ligger över sitt 50- respektive 200-dagars medelvärde.

## Begränsningar att känna till
- **Datakälla:** Yahoo Finance via `yfinance`. Det är ett inofficiellt gränssnitt, så det kan ibland sluta fungera eller ge fel/fördröjd data. Avanza saknar öppet API; vill du koppla in en annan källa skriver du en klass med metoderna `history()` och `fundamentals()` i `app/providers.py`.
- **Kvartalsrapporter:** sammanfattningarna byggs av rapporterade nyckeltal (omsättning, marginaler, resultat, EPS mot förväntan). De återger inte ledningens kommentarer, riktlinjer eller bolagets egen text. För det behöver du läsa rapporten själv eller ge Claude rapporttexten. Anteckningsrutan på aktiesidan följer med i exporten. Yahoo ger oftast bara de senaste 4–5 kvartalen, och täckningen för mindre bolag är sämre. ETF:er och index har inga rapporter.
- **Ingen investeringsrådgivning:** signalbetyget och mätetalen är beskrivande och bygger på regler jag har valt, inte på historisk testning. Backtesten är ett test mot historien, inget löfte om framtiden.
- **Testat:** logik, gränssnitt och dataflöde är testade med demo-data, och Yahoo-delen är testad mot låtsas-objekt med yfinance-format. Den har inte körts mot Yahoo live, så första körningen är den verkliga provningen. Fel per ticker visas under ⚙ Inställningar.

## Filer
```
run.py            startskript (--demo, --port, --no-browser)
app/              backend (FastAPI): db, providers, metrics, indicators, signals, backtest, journal, portfolio, macro, game, quizdata, exercises, paper, digest, snapshot, scheduler, seed
static/           gränssnittet (HTML/CSS/JS; glossary.js är ordlistan, views2.js Makro/Backtest/Journal/Portfölj, practice.js Öva och Övningsportfölj, game.js spelläget; Chart.js ligger lokalt, inget laddas från internet)
data/             skapas vid körning: databas + export
```
Ta bort `data/marknadsradar.db` för att börja om från förvalda listor.

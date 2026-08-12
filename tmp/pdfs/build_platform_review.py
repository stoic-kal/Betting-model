from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from datetime import date
import os

OUT = "/Users/kalyaan/betting-model/output/pdf/jingleez_platform_technical_review.pdf"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

NAVY = colors.HexColor("#14213D")
BLUE = colors.HexColor("#2563EB")
TEAL = colors.HexColor("#0F766E")
RED = colors.HexColor("#B42318")
AMBER = colors.HexColor("#B54708")
LIGHT = colors.HexColor("#F4F6F8")
MID = colors.HexColor("#D0D5DD")
DARK = colors.HexColor("#1D2939")
MUTED = colors.HexColor("#667085")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=25, leading=30, textColor=NAVY, alignment=TA_LEFT, spaceAfter=18))
styles.add(ParagraphStyle(name="CoverSub", parent=styles["Normal"], fontSize=12, leading=18, textColor=MUTED, spaceAfter=12))
styles.add(ParagraphStyle(name="H1x", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=17, leading=21, textColor=NAVY, spaceBefore=8, spaceAfter=10))
styles.add(ParagraphStyle(name="H2x", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=BLUE, spaceBefore=9, spaceAfter=5))
styles.add(ParagraphStyle(name="Bodyx", parent=styles["BodyText"], fontSize=9.2, leading=13.2, textColor=DARK, spaceAfter=6))
styles.add(ParagraphStyle(name="Smallx", parent=styles["BodyText"], fontSize=7.6, leading=10.2, textColor=MUTED, spaceAfter=3))
styles.add(ParagraphStyle(name="TableHeader", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7.8, leading=10, textColor=colors.white, spaceAfter=0))
styles.add(ParagraphStyle(name="Callout", parent=styles["BodyText"], fontSize=10, leading=14, textColor=NAVY, borderColor=BLUE, borderWidth=1, borderPadding=9, backColor=colors.HexColor("#EFF6FF"), spaceBefore=6, spaceAfter=10))
styles.add(ParagraphStyle(name="Verdict", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=colors.white, backColor=NAVY, borderPadding=10, spaceAfter=10))
styles.add(ParagraphStyle(name="Bulletx", parent=styles["BodyText"], fontSize=9, leading=12.5, leftIndent=12, firstLineIndent=-7, bulletIndent=3, spaceAfter=3))

def P(text, style="Bodyx"):
    return Paragraph(text, styles[style])

def bullet(text):
    return Paragraph("&#8226; " + text, styles["Bulletx"])

def table(rows, widths, header=True, small=False):
    data = []
    for i, row in enumerate(rows):
        style = "TableHeader" if header and i == 0 else ("Smallx" if small else "Bodyx")
        data.append([P(str(c), style) for c in row])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("GRID", (0,0), (-1,-1), 0.35, MID),
        ("LEFTPADDING", (0,0), (-1,-1), 5), ("RIGHTPADDING", (0,0), (-1,-1), 5),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]
    if header:
        commands += [("BACKGROUND", (0,0), (-1,0), NAVY), ("TEXTCOLOR", (0,0), (-1,0), colors.white)]
    for i in range(1 if header else 0, len(data)):
        if i % 2 == 0: commands.append(("BACKGROUND", (0,i), (-1,i), LIGHT))
    t.setStyle(TableStyle(commands))
    return t

def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(MID); canvas.line(0.65*inch, 0.55*inch, 7.85*inch, 0.55*inch)
    canvas.setFont("Helvetica", 7.5); canvas.setFillColor(MUTED)
    canvas.drawString(0.65*inch, 0.35*inch, "Jingleez MLB Betting Platform - Independent Technical Review")
    canvas.drawRightString(7.85*inch, 0.35*inch, f"Page {doc.page}")
    canvas.restoreState()

story=[]
story += [Spacer(1,0.65*inch), P("JINGLEEZ MLB BETTING PLATFORM", "CoverSub"), P("Technical Review and Owner's Learning Guide", "CoverTitle")]
story += [P("Principal ML Engineering | Quantitative Research | Data Engineering | MLOps | Software Architecture", "CoverSub"), Spacer(1,0.25*inch)]
story += [P("CURRENT VERDICT", "H2x"), P("A sophisticated research platform with unusually strong point-in-time discipline and diagnostic breadth - but not yet a proven production betting operation.", "Verdict")]
story += [P("The strongest part of the project is its refusal to fabricate missing history and its increasingly evidence-gated research process. The weakest part is the gap between research artifacts and economically trustworthy live operation: only 254 resolved picks exist, legacy execution did not record realized stakes, the corrected totals engine has no resolved live sample, and recent notification failures exposed how easily test and production boundaries can blur.", "Callout")]
story += [Spacer(1,0.25*inch), table([
    ["Dimension","Assessment","Plain-language meaning"],
    ["Data platform","Strong foundation","Canonical identities, immutable history, hashes, quarantine, and leakage gates are real strengths."],
    ["ML evidence","Mixed","Historical moneyline signal is modest; totals discrimination is near random in the long historical benchmark."],
    ["Betting evidence","Not established","Theoretical returns exist, but historical realized stakes do not."],
    ["Production reliability","Improving, still fragile","The grading incident is fixed, but SQLite + in-process scheduling remains a single-host design."],
    ["Overall maturity","Advanced hobby / early research platform","Good enough to learn and shadow trade; not enough evidence for confident bankroll scaling."],
], [1.25*inch,1.35*inch,4.55*inch])]
story += [Spacer(1,0.35*inch), P("Prepared 11 August 2026 from repository code, databases, model registry metadata, generated diagnostics, and prior experiment reports.", "Smallx"), PageBreak()]

story += [P("How to read this report", "H1x")]
story += [P("Each conclusion is labeled implicitly by its evidence level:")]
for x in ["<b>Verified:</b> directly supported by code, database counts, registry metadata, or a completed report.","<b>Interpretation:</b> a professional judgment derived from multiple verified facts.","<b>Insufficient evidence:</b> the platform does not yet contain the sample, timestamps, or executed-wager history needed for a valid conclusion."]:
    story.append(bullet(x))
story += [P("Snapshot of where you are", "H2x"), table([
    ["Area","Verified snapshot"],
    ["Codebase","42 service modules / 12,936 lines; 34 pipeline modules / 9,146 lines; 9 diagnostics modules / 3,684 lines."],
    ["Historical warehouse","23,168 canonical games; 22,764 market games; 99.84% exact Retrosplits join coverage."],
    ["Historical player history","673,377 player-game rows plus 46,264 team-game rows for 2012-2021."],
    ["Live pick database","274 picks: 140 won, 114 lost, 3 push, 9 void, 8 pending."],
    ["Validated production history","254 resolved picks; realized-stake coverage for legacy resolved picks is 0%."],
    ["Current service","Single launchd process, singleton application lock, one in-process automation worker."],
], [1.7*inch,5.45*inch])]

story += [P("1. Complete system mental model", "H1x"), P("The platform currently contains two related but not fully unified systems:")]
story += [table([
    ["Layer","What it does","Important boundary"],
    ["Historical platform","Ingests Retrosplits and Vegas closing odds; creates canonical games and point-in-time team features.","Excellent for research, but 2012-2021 schemas differ from modern live inference."],
    ["Modern feature pipeline","Builds Statcast, pitcher, hitter, lineup, bullpen, weather, park, travel, and market context.","Richer features, much smaller modern labeled sample."],
    ["Training / registry","Chronological training, calibration, diagnostics, registry metadata, promotion reports.","Many artifacts exist; model lineage is richer than deployment governance."],
    ["Live inference","MLB schedule + confirmed lineups + sportsbook odds feed moneyline and totals decisions.","Official picks lock; previews are separate from persisted wagers."],
    ["Execution / tracking","Kelly sizing, exposure limits, SQLite picks, grading, Discord, analytics.","Realized stake tracking begins only now; legacy bankroll claims are theoretical."],
], [1.2*inch,3.55*inch,2.4*inch], small=True)]
story += [P("Architectural truth", "H2x"), P("The repository has grown by accretion. It includes a modern service layer, older root scripts, a separate historical warehouse, multiple model schemas, many generated reports, and a Flask application that also owns scheduling. The components are individually capable, but the system lacks one explicit orchestration boundary and one authoritative domain model for Game, Prediction, Wager, Grade, and Notification.")]

story += [P("2. Architecture review", "H1x")]
story += [P("What is excellent", "H2x")]
for x in ["Source hashing, immutable history, quarantine instead of fuzzy guessing, and point-in-time shifts are production-minded decisions.","Separation into pipeline, services, routes, diagnostics, registry, and reports is directionally correct.","The project records negative results. The feature-discovery run rejected 239 of 244 target-feature candidates instead of promoting availability as signal.","The new grading transaction and notification outbox establish real correctness invariants."]:
    story.append(bullet(x))
story += [P("What is fragile", "H2x")]
for x in ["Flask serves HTTP and starts a scheduler thread. A web process should not also be the job orchestrator in a durable production design.","SQLite is acceptable for one machine and modest traffic, but schema migration, queueing, model state, analytics, and operational locks all share one file.","Configuration is distributed across environment variables, config.py, launchd files, constants, registry pointers, and report artifacts.","A large dirty working tree and numerous generated artifacts in the repository make reproducibility and rollback harder than the model code itself.","Legacy entry points still exist (root scripts, production_runner.py, maintenance scripts). Even when not active, they enlarge the incident surface."]:
    story.append(bullet(x))
story += [P("Professional recommendation", "Callout"), P("Do not add another abstraction layer yet. First define five authoritative records - Game, Prediction, Wager, Grade, Notification - and make every service use them. Then separate the web server, scheduler, and worker processes. This reduces risk more than another model family.")]

story += [PageBreak(), P("3. Machine-learning review", "H1x")]
story += [table([
    ["Question","Evidence","Verdict"],
    ["Does moneyline contain signal?","Historical four-fold AUC 0.5991-0.6274; historical Extra Trees AUC 0.6129. Modern registry champion test AUC 0.5393.","Yes historically, but modern signal is modest and schema comparability is unresolved."],
    ["Does totals contain signal?","Historical folds AUC 0.5008-0.5156; best ensemble test AUC 0.5203. Modern registry AUC 0.5441.","Weak. Treat as research/shadow until current corrected live evidence accumulates."],
    ["Is calibration solved?","Moneyline raw metrics beat calibrated metrics in the latest registry test; totals live ECE attribution is entirely legacy input.","No. Selection and evaluation layers need clearer separation; do not smooth ECE blindly."],
    ["Are features evidence-gated?","Only 2/122 moneyline and 3/122 totals transformations survived a 3-of-4 fold log-loss gate.","This is one of the strongest practices in the project."],
    ["Is promotion trustworthy?","Historical challenger retained behind current champion due schema mismatch and zero shadow outcomes.","Decision was correct; promotion needs unified shadow contracts."],
], [1.3*inch,3.75*inch,2.1*inch], small=True)]
story += [P("Where the project is overengineering", "H2x")]
for x in ["Running many model families when the label, market timestamp, and feature-time contracts dominate the error budget.","Producing extensive diagnostic artifacts faster than decisions can be validated on independent live samples.","Revisiting calibration, blending, or disagreement rules when prior walk-forward evidence already rejected promotion."]:
    story.append(bullet(x))
story += [P("Where the project is underengineering", "H2x")]
for x in ["Dataset contracts between historical training and live inference are not yet one executable schema.","Model artifacts show a scikit-learn version mismatch warning between training and serving environments.","There is no single reproducible release unit binding code commit, environment lock, dataset hash, feature schema, model artifact, and migration version.","The latest moneyline metadata says sigmoid was selected, yet the reported raw test Log Loss/Brier/ECE are better than calibrated values. This needs a clean nested selection audit, not a new calibrator."]:
    story.append(bullet(x))

story += [P("4. Data review", "H1x")]
story += [P("The historical warehouse is the most production-grade part of the project. It correctly treats postgame participants as unavailable pregame information, quarantines source disagreement, and shifts completed-game features. The rebuilt dataset reports zero remaining duplicate groups after the earlier 406-row corruption was corrected.")]
story += [table([
    ["Data domain","Current state","Information still lost"],
    ["Games / identity","Canonical source identity, doubleheaders, suspended dates, quarantine.","Not every 2012-2021 source game has MLB gamePk."],
    ["Market","91,056 closing outcomes; live snapshots exist.","Historical entry-to-close movement and true CLV are unavailable."],
    ["Lineups","Live confirmed lineup intelligence exists; Statcast postgame reconstructions exist.","No timestamped historical pregame lineup archive; historical lineup experiment correctly blocked."],
    ["Weather","Modern context available.","No historical pregame forecast archive; observed weather cannot safely substitute."],
    ["Bullpen","Shifted history and recent workload features exist.","Historical active-reliever availability and roster state remain weak."],
    ["Starters / hitters","Modern Statcast features and rolling histories are extensive.","Modern sample is small; cross-era player identity and lineup coverage do not align with Vegas history."],
], [1.2*inch,2.8*inch,3.15*inch], small=True)]
story += [P("Highest-value missing data", "H2x"), P("The highest-ROI missing dataset remains timestamped pregame lineup snapshots. Second is multi-timestamp historical odds. Third is historical pregame weather forecasts and active bullpen availability. Do not substitute postgame lineups or observed weather; that would make backtests look better while making the product worse.")]

story += [PageBreak(), P("5. Betting and bankroll review", "H1x")]
story += [P("Is this acting like a good bettor or a good classifier?", "Verdict"), P("Historically, mostly a classifier with betting outputs. The new execution controls move it toward a betting system, but trustworthy bankroll evidence starts now, not retroactively.", "Callout")]
story += [table([
    ["Metric","Observed","Interpretation"],
    ["Resolved history","254 picks","Too small for stable segment and tail-risk conclusions."],
    ["Realized legacy stake coverage","0%","Historical ROI using Kelly units is theoretical, not executed performance."],
    ["Simultaneous ML/totals pairs","105","Win-indicator correlation 0.0305; both lost in 21.9%. Useful but still small."],
    ["Theoretical max game exposure","2.0 units","Exceeded the new 1.0-unit game limit historically."],
    ["Theoretical max daily exposure","24.0 units","Far beyond the new 5.0-unit daily cap."],
    ["Theoretical max drawdown","3.532 units","Descriptive only because realized stakes were not recorded."],
    ["Theoretical 95% CVaR","-3.0495 units/day","Tail estimate is unstable across only 11 active days."],
], [2.15*inch,1.55*inch,3.45*inch], small=True)]
story += [P("What good betting behavior now requires", "H2x")]
for x in ["Record offered price, accepted price, theoretical Kelly, realized stake, limits applied, rejection reason, and closing price as distinct fields.","Evaluate decisions by calibration and CLV first, then ROI after enough independent bets; never optimize production thresholds on the same sample.","Treat moneyline and total wagers on one game as a shared exposure to game state, even if historical binary correlation looks small.","Scale bankroll only after a predeclared shadow/live protocol reaches an adequate sample and survives drawdown expectations."]:
    story.append(bullet(x))

story += [P("6. Diagnostics review", "H1x")]
story += [table([
    ["Diagnostic","Value","Judgment"],
    ["Walk-forward Log Loss/Brier","High","Core decision metrics; retain."],
    ["Calibration attribution with Wilson intervals","High","Actionable when repeated across folds and live shadow."],
    ["Permutation + LOFO + stability","High","Good promotion evidence when computed strictly inside folds."],
    ["CLV","Potentially high","Currently limited because historical platform has closing-only observations."],
    ["ROI by small segment","Low to medium","Exploratory; easily becomes multiple-testing noise."],
    ["Large dashboard metric inventories","Mixed","Useful only if each metric owns a decision and alert threshold."],
    ["Win rate without price/context","Low","A vanity metric when presented alone."],
], [2.0*inch,1.25*inch,3.9*inch], small=True)]
story += [P("Totals distribution finding", "H2x"), P("On 85 legacy totals rows with expected and actual runs, actual variance was 19.66 against mean 8.87 (variance-to-mean 2.22). Poisson intervals undercover: 80% nominal covered 65.9%, 90% covered 81.2%, and 95% covered 85.9%. This is evidence that mean-only and Poisson diagnostics are inadequate. It is not evidence against the corrected totals engine because corrected-input resolved rows equal zero.")]
story += [P("Diagnostics still missing", "H2x")]
for x in ["A predeclared experiment registry that prevents repeated hypothesis fishing across the same folds.","Uncertainty on economic metrics via block/bootstrap methods that preserve day and game dependence.","Data-contract monitoring comparing live feature distributions and missingness against the exact champion training schema.","End-to-end decision latency, odds staleness, rejected-wager counts, and notification/outbox service-level metrics."]:
    story.append(bullet(x))

story += [PageBreak(), P("7. Production and incident review", "H1x")]
story += [P("The August 11 Discord incident", "H2x"), P("The false Yankees loss and Nationals/Phillies push were generated by regression fixtures that imported the real Discord service while using temporary databases. Repeated test runs produced repeated production messages. A separate production flaw also allowed resolved rows with missing actual totals to be selected again. Two launchd plists pointed to the application, although only one was loaded.")]
story += [table([
    ["Invariant","Before","Now"],
    ["Only MLB Final grades","Partial","Direct MLB schedule call requires abstractGameState exactly Final."],
    ["One grade per pick","No hard guarantee","Transaction plus UPDATE WHERE status='pending'."],
    ["One result row","Application-level check","Unique index on results.pick_id."],
    ["One notification","No production flag/outbox","Transactional outbox, unique keys, atomic claim, Discord nonce."],
    ["Tests cannot notify production","False","Non-production database delivery disabled."],
    ["One scheduler","Latent duplicate launchd config","Legacy plist disabled plus process singleton lock."],
    ["Push immutability","Not explicit","Resolved statuses are excluded; explicit reversal would be required."],
], [1.8*inch,2.35*inch,3.0*inch], small=True)]
story += [P("Remaining production risks", "H2x")]
for x in ["The outbox and scheduler are still embedded in the Flask host. A machine restart, disk issue, or long-running feature fetch affects both UI and automation.","SQLite backups, integrity checks, retention, and restore drills are not yet a visible operational routine.","Logging is largely text output; there is no structured correlation ID spanning prediction, wager, grade, and notification.","Dependency ranges are broad rather than locked, while logs already show model-serving version mismatch warnings.","The notification outbox begins empty because historical sends were not safely backfilled. That is honest, but historical delivery cannot be proven."]:
    story.append(bullet(x))

story += [P("8. Research directions ranked by expected impact", "H1x")]
story += [table([
    ["Rank","Direction","Why it fits","Do not proceed until"],
    ["1","Unified probabilistic run model (Negative Binomial / hierarchical)","Observed totals are materially overdispersed; produces coherent total, interval, team-score, and alternate-line probabilities.","Corrected live outcomes and point-in-time inputs accumulate."],
    ["2","Timestamped lineup state + player aggregation","Personnel changes are information team rolling averages cannot represent.","A genuine pregame publication timestamp exists."],
    ["3","Market microstructure","Entry-to-close movement, book dispersion, and quote age directly affect bet quality.","Multiple timestamped historical books are available."],
    ["4","Hierarchical partial pooling","Stabilizes early-season/player/team estimates and sparse platoon contexts.","One unified feature-time contract exists."],
    ["5","Monte Carlo game simulation","Useful after team-run distributions and dependence are calibrated.","Distribution model passes interval/PIT diagnostics."],
    ["6","Player embeddings / pitch-level sequence models","Potential long-run signal, but high complexity and identity burden.","Simpler lineup and hierarchical baselines are exhausted."],
], [0.45*inch,1.65*inch,3.2*inch,1.85*inch], small=True)]
story += [P("Stop doing this", "H2x")]
for x in ["Stop adding model families merely because they are supported.","Stop interpreting tiny ROI slices as strategy evidence.","Stop reopening rejected calibration/blending experiments without new chronological data.","Stop treating generated reports as progress unless they change a predeclared decision.","Do not pursue reinforcement learning, causal inference, graph neural networks, Gaussian Processes, or mixture-density networks yet. Their expected value is below fixing data-time contracts and distribution modeling."]:
    story.append(bullet(x))

story += [PageBreak(), P("9. Blind spots and uncomfortable truths", "H1x")]
for title, text in [
    ("The market is already a strong model","Historical moneyline market Log Loss was better overall in three of four folds. Your model must beat a highly informed baseline after vig, latency, limits, and selection - not merely predict winners."),
    ("Backtest comparability is fractured","The 2012-2021 historical platform and modern Statcast champion use different feature schemas and eras. A better number on one is not automatically a better deployable model."),
    ("Sample size is the governing constraint","With 254 resolved picks and zero corrected totals resolutions, many sophisticated live diagnostics are descriptions of uncertainty, not answers."),
    ("Operations can invalidate research","A perfect backtest is irrelevant if tests can notify production, workers race, odds are stale, or realized stakes are unknown. The recent incident demonstrated this directly."),
    ("Selection bias is everywhere","Evaluating only official picks, high-EV picks, disagreement tails, or losses can distort conclusions. Preserve every candidate prediction and every no-bet reason."),
    ("The hardest problem is not classification","It is estimating a small conditional edge, obtaining the quoted price, sizing under uncertainty, and surviving variance without changing rules after losses."),
]:
    story += [P(title,"H2x"), P(text)]
story += [P("If this were my own money", "Verdict"), P("I would not scale stakes yet. I would run the corrected moneyline and totals systems in shadow or minimal fixed-risk mode until realized execution, closing prices, corrected-input outcomes, and operational reliability are demonstrated over a predeclared sample. I would trust the data engineering trajectory more than the current live edge estimate.", "Callout")]

story += [P("10. Roadmaps", "H1x")]
story += [P("Roadmap A - one weekend", "H2x")]
for x in ["Freeze a release: clean working tree, tagged commit, locked environment, database backup, model/dataset hashes, and rollback instructions.","Create one operational dashboard: worker heartbeat, last MLB poll, last successful grade, outbox depth, failed sends, odds rejections, pending games, and database integrity.","Write the canonical lifecycle states for Game, Prediction, Wager, Grade, and Notification; add transition tests.","Start a forward-only evaluation ledger recording every prediction, no-bet, quote, realized stake, and close."]:
    story.append(bullet(x))
story += [P("Roadmap B - one month", "H2x")]
for x in ["Separate Flask, scheduler, and worker processes; keep SQLite only if single-host throughput remains adequate, otherwise move operational state to Postgres.","Build one executable feature schema shared by training, shadow, and live inference with drift/missingness alarms.","Implement a Negative Binomial totals baseline and compare distributional Log Score, CRPS, PIT, interval coverage, and betting metrics on expanding folds.","Create a formal experiment ledger with hypothesis, data cutoff, folds, primary metric, promotion gate, and result to stop experiment repetition.","Run restore drills and notification failure drills; document operational runbooks."]:
    story.append(bullet(x))
story += [P("Roadmap C - one year", "H2x")]
for x in ["A unified event-sourced baseball warehouse with immutable source snapshots and point-in-time feature views.","Timestamped lineups, odds across books, weather forecasts, roster/availability, and quote latency integrated under one game identity.","Hierarchical player/team priors feeding coherent run distributions and Monte Carlo pricing across moneyline, totals, and alternate markets.","A true champion/challenger platform with shadow deployment, sequential monitoring, automated rollback, and reproducible releases.","Portfolio optimization based on joint game-level scenarios, market limits, uncertainty-aware Kelly fractions, and realized execution quality."]:
    story.append(bullet(x))

story += [PageBreak(), P("Final answer: what I would do next", "H1x"), P("I would stop model expansion and build the forward-only evidence and release layer.", "Verdict")]
story += [P("Why", "H2x"), P("The project already has enough features, models, diagnostics, and historical experiments to show that the remaining uncertainty is not 'which classifier should I try?' The uncertainty is whether the exact live system - with corrected features, obtainable prices, realized stakes, and reliable operations - produces repeatable calibration and closing-line value. Until that is measured, additional model complexity mostly creates more ways to overfit and more artifacts to maintain.")]
story += [P("My sequence would be:")]
for x in ["1. Freeze and reproduce one production release.","2. Capture every live decision and execution field without gaps.","3. Accumulate corrected totals and moneyline shadow/live outcomes under unchanged rules.","4. In parallel, test a simple overdispersed totals distribution model, because current run intervals demonstrably fail.","5. Revisit promotion only when forward evidence reaches the predeclared threshold."]:
    story.append(bullet(x))
story += [P("This is already good enough", "H2x"), P("The project is good enough to be a serious learning laboratory, to generate disciplined shadow predictions, and to support careful low-risk live observation. Its data-quality instincts are stronger than many commercial prototypes.")]
story += [P("This is not yet good enough", "H2x"), P("It is not yet good enough to claim a stable edge, estimate a scalable bankroll growth rate, or increase wagers based on historical ROI. That conclusion is not pessimism; it is what the available evidence supports.")]

story += [P("Appendix A - evidence register", "H1x")]
sources = [
    ["Evidence","Repository location"],
    ["Historical platform coverage and champion decision","reports/data_platform/final_engineering_report.md"],
    ["Existing-data feature acceptance/rejection","reports/data_platform/existing_data_discovery/final_report.md"],
    ["Segment and market comparison","reports/data_platform/segment_market_diagnostics/final_report.md"],
    ["Meta-calibration rejection","reports/data_platform/totals_meta_calibration/final_report.md"],
    ["Disagreement taxonomy","reports/data_platform/disagreement_taxonomy/final_report.md"],
    ["Complete execution audit","reports/execution/complete_execution_audit.json"],
    ["Calibration attribution","reports/diagnostics/calibration_attribution.md"],
    ["Run distribution diagnostics","reports/diagnostics/totals_run_distribution.json"],
    ["Modern champions","models/registry/moneyline/latest.json; models/registry/totals/latest.json"],
    ["Dataset dedup status","data/dataset_version.json"],
    ["Production grading / outbox","src/update_results.py"],
    ["Scheduler and launch control","services/automation_service.py; app.py; LaunchAgents"],
]
story += [table(sources,[2.5*inch,4.65*inch],small=True)]

doc = SimpleDocTemplate(OUT, pagesize=letter, rightMargin=0.65*inch, leftMargin=0.65*inch, topMargin=0.62*inch, bottomMargin=0.72*inch, title="Jingleez MLB Betting Platform Technical Review", author="Codex")
doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
print(OUT)

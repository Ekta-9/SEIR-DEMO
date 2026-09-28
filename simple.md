# SEIR — Explained Simply

*A plain-language guide to the SEIR project and to my part in it (Data/Evolution + AI Explanation).*

---

## Part 1 — What is SEIR?

### The house analogy

Imagine a big, old house full of wiring. You want to **remove one light switch**. Before you pull it out, you would want to know:

- Which lights does this switch control?
- Is anything *secretly* connected to it?
- Has anyone actually used it recently?
- How risky is it to remove?

**Software is just like that house.** A big program is made of thousands of pieces (we call them **components** — in our case, one Java class = one piece). These pieces are connected to each other. When a developer wants to change or delete one piece, they often don't know what else will break.

> **SEIR answers one question:**
> *"If I change or delete this piece of code, what could break — and how risky is it?"*

### How SEIR finds the answer

SEIR works like a **detective**. It collects clues from four places:

| Clue source | What it means | In the house analogy |
|---|---|---|
| **The code** | Which pieces directly use this piece | Looking at the visible wires |
| **Settings files** (config) | The piece is mentioned by name in a settings file, not in code | A note in the fuse box saying "switch 7 = garage" |
| **History** (Git) | How often it changed, who changed it, what changed along with it | The house's repair logbook |
| **Live usage** (runtime) | Whether the piece is actually used while the program runs | Watching which lights people actually switch on |

Then SEIR:

1. Puts all clues together into a **map** of connections.
2. Works out **what could be affected** (the "blast radius").
3. Gives a **risk level**: LOW, MEDIUM or HIGH.
4. Writes a **plain-English explanation** — e.g. *"Nobody seems to use this anymore, but a settings file still mentions it. Check that before deleting."*
5. Shows everything on a **website dashboard**.

### The big research question

> Do the extra clues (history, settings, live usage) actually help — or is just reading the code good enough?

We don't assume the answer. We **test** it and report whatever we find, even if the answer is "no, they didn't help much."

---

## Part 2 — The Team (a factory line)

```
 [Code Reader]              [Clue Collector — ME]
  Member 4                   Member 5
  reads the code,            reads history, settings,
  draws the map              live usage
        \                        /
         ▼                      ▼
        ┌──────────────────────────┐
        │    All clues together    │
        └──────────────────────────┘
          │                    │
          ▼                    ▼
   [Risk Predictor]       [Explainer — ME]
    Member 3               writes the plain-English
    says LOW / MED / HIGH  explanation
          \                    /
           ▼                  ▼
        [Backend — Member 2]   stores everything, connects parts
                 │
                 ▼
        [Website — Member 1]   shows it to the user
```

| Member | Role | In simple words |
|---|---|---|
| 1 | Frontend | Builds the website the user sees |
| 2 | Backend | The "post office" — connects all parts and stores data |
| 3 | AI/ML | Builds the model that says LOW / MEDIUM / HIGH |
| 4 | Software Analysis | Reads the code and draws the connection map |
| **5** | **Data/Evolution + AI (ME)** | **Collects extra clues, builds practice data, writes explanations** |

---

## Part 3 — How a user uses SEIR (step by step)

1. **Opens the SEIR website.**
2. **Pastes a GitHub link** to their project (and optionally uploads usage logs if they have them).
   - A GitHub link is better than a zip file because it includes the **full change history** — which my part needs.
3. **Waits a few minutes** while SEIR analyzes the project. They see a progress screen:
   ```
   ✅ Downloading code and history
   ✅ Reading the code, finding connections
   ⏳ Reading change history          ← MY PART
   ⬜ Reading settings files          ← MY PART
   ⬜ Reading usage logs (if any)     ← MY PART
   ⬜ Calculating risk
   ```
4. **Sees a project overview** — number of pieces, riskiest pieces, a search box.
5. **Picks a piece** (e.g. `LegacyPaymentService`) and says what they want to do: *modify / delete / deprecate*.
6. **Sees the result page:**
   - Risk level (from Member 3)
   - What could break + connection map (from Member 4)
   - **Clues box** — history, settings, usage (**from me**)
   - **Explanation** (**from me**)
   - **Checklist before you delete** (**from me**, built from my clues)
   - **History timeline** (**from me**)
7. **Investigates and decides** whether to make the change. Can come back and re-analyze later.

---

## Part 4 — My Part: the three jobs

### Job 1 — Collect the extra clues

Everything **except** the code itself:

- 📜 **History** — how active each piece is.
- ⚙️ **Settings** — where each piece is mentioned in settings files.
- 🏃 **Live usage** — whether each piece is actually used while the program runs.

### Job 2 — Build the practice data (the MOST important job)

Member 3's risk model is a machine-learning model. It learns from **examples**, like a student learning from solved exam questions. **I prepare those solved questions:**

- "Here is a change someone made in the past."
- "Here are the clues that existed **before** the change."
- "Here is what **actually happened after** — did things break or not?"

Without this, Member 3 can't train anything. So I should give them a **first version early**.

### Job 3 — The Explainer

Take all the clues and use an AI (like Claude or ChatGPT) to write a short, honest explanation for the developer.

**The golden rule for the AI:** it may only say things backed by a clue. **No making things up.**

---

## Part 5 — My evaluation report, in plain words

My official report ("Data & Evolution Evaluation") is about **proving my clues are correct and useful**. Here is what each section really means.

### 5.1 Two big questions

My report asks two separate things:

1. **Did I collect the clues correctly?** (Is my history counter counting right? Did my settings reader find the right mentions?)
2. **Do the clues actually help?** (Does the risk prediction get better because of them?)

These are different. A clue can be collected perfectly and still be useless. So I check both.

### 5.2 The six research questions (RQ-D1 to RQ-D6) — simplified

| Code | Fancy name | What it really asks |
|---|---|---|
| RQ-D1 | Git reliability | Can I correctly match history to each piece of code and count things right? |
| RQ-D2 | Configuration coverage | Can I find the places where settings files mention a piece? |
| RQ-D3 | Runtime quality | Does my usage data correctly show which pieces are used? |
| RQ-D4 | Multi-source usefulness | Do my extra clues tell us something the code alone doesn't? |
| RQ-D5 | Predictive usefulness | Does the risk model get better with my clues? |
| RQ-D6 | Explanation usefulness | Do my structured clues help the AI write better, more honest explanations? |

### 5.3 Picking the projects to study

I need a few free, open-source **Java** projects that:

- have a long change history,
- are allowed to be used (licence is OK),
- have enough information to tell what happened after a change.

**Good starting choice:** *Spring PetClinic* (small demo app of a vet clinic) + 3–5 bigger Java projects.

### 5.4 History clues (Git)

From the project's history I read, for every past change: its ID, date, author, which files it touched, and how many lines were added/removed.

From that I calculate, for each piece:

| Clue | Plain meaning |
|---|---|
| recent_commit_count | How many times it changed recently (e.g. last 90 days) |
| historical_commit_count | How many times it changed ever |
| days_since_last_change | How long since anyone touched it |
| unique_contributors | How many different people worked on it |
| lines_added / lines_deleted | How much code was added / removed over time |
| total_churn | Added + removed (how "busy" it is) |
| co-change_count | Which other pieces usually change at the same time |

**How I check I did it right:**
- Pick some pieces and **count by hand**, then compare with my program.
- **Run it twice** on the same project — the results must be identical.
- Watch out for **renamed files** — if a file was renamed, its history must not be lost.

### 5.5 Settings clues (Config)

Settings files (`application.yml`, `.properties`, `.xml`) often mention pieces of code by name — for example a scheduled job, or a class name as text. These links are **invisible** if you only read the code.

**How I check I did it right:**
1. Pick some settings files.
2. **By hand**, write down every real mention.
3. Run my program.
4. Compare: how many did it find correctly? how many did it miss? how many were wrong?
5. Keep a separate list of mentions I **couldn't match** to any piece ("unresolved").

**Important:** "Mentioned in settings" ≠ "definitely used". It's a **possible** link, not proof.

### 5.6 Live usage clues (Runtime)

This records which pieces **actually ran** while the app was being used.

Real projects don't share their usage logs, so **I create my own**:
1. Run PetClinic on my computer.
2. Attach a free recording tool (**OpenTelemetry**) that notes which pieces run.
3. Use a script of **fake users** (**Locust**) that click around the app.
4. Because I wrote the fake-user script, I **already know** which pieces should appear — so I can check whether the recorder caught them.

**The #1 rule of usage data:**

> **"Not seen being used" does NOT mean "never used."**
> Maybe my fake users just didn't click that button.

So I always record **how long** I watched and **how much** of the app was covered:

| Coverage | Meaning |
|---|---|
| High | Most of the app was exercised — "not seen" means something |
| Partial | Some parts were exercised |
| Low / unknown | "Not seen" means very little |
| Unavailable | No usage data at all |

### 5.7 One standard format for every clue

Code, history, settings and usage all "speak different languages". So every clue gets written in **one standard shape**:

```
Clue {
  piece:        LegacyPaymentService
  source:       GIT            (or CONFIG / RUNTIME / STATIC)
  clue type:    recent_commit_count
  value:        2
  time window:  last 90 days
  proof:        change IDs abc123, def456     ← "where did this come from?"
  available?:   yes / no / unknown
  method:       how I extracted it
}
```

The **proof** part is essential — later, the Explainer must be able to point back to real evidence.

Also: **"unknown" is not the same as 0.** If I have no usage data, I must not write "used 0 times" — I write "unknown".

### 5.8 Data quality checks

Before giving data to Member 3, I check it like a teacher checking homework:

| Check | Question |
|---|---|
| Completeness | Is anything missing? |
| Accuracy | Does it match the real source? |
| Consistency | Is the same piece named the same way everywhere? |
| Timeliness | Is it from the right time period? |
| Uniqueness | Any duplicates? |
| Validity | Are values sensible (no negative counts, etc.)? |
| Traceability | Can I trace every clue back to its proof? |

For every version of the dataset I write down: how many projects, pieces, examples, missing values, unresolved mentions, and removed records.

### 5.9 Ground truth — the "answer key" (VERY important)

To train and test a model, I need the **correct answers** — called **ground truth**. Like the answer key for an exam.

**Where can correct answers come from?**
- Past changes where we can see what else had to change.
- Bug-fix changes that came soon after (meaning the change broke something).
- Tests that failed.
- Experts labelling by hand.
- Controlled experiments — I delete a piece myself and see what breaks.

**My practical plan:**
- For each past change to a piece → look at **how many other pieces had to change** with it, and **whether a bug fix followed soon after**.
- Turn that into a label, e.g.:
  - **LOW** = almost nothing else changed, no bug fix
  - **MEDIUM** = a few other pieces changed, or a small fix was needed
  - **HIGH** = many pieces changed, or a fix that touched other pieces
- Write down these rules **before** training and never change them afterwards.

**Rule:** the answer key must NOT be made from the same clues the model uses — otherwise it's like giving a student the answers inside the question.

### 5.10 Features — the clues the model learns from

"Features" is just the ML word for **clues, turned into numbers**:

| Family | Examples |
|---|---|
| Structural (Member 4) | how many pieces depend on it, how deep the chain goes |
| Evolution (me) | recent changes, days since change, contributors, churn |
| Configuration (me) | how many settings mentions, of what type |
| Runtime (me) | used or not, how often, how well-covered |
| External | might something outside the project use it? |
| Complexity | size of the code, how complicated it is |

Checks on features: look for weird extreme values, missing values, duplicates, and — most importantly — **any accidental "future" information**.

### 5.11 No cheating (leakage)

**Leakage = accidentally giving the model information from the future.** It makes results look amazing but they are fake.

> **Golden rule:** When I make an example about a past change, I only use clues from **before** that change.

Other ways to cheat by accident:
- Testing on almost the same code the model was trained on.
- Randomly mixing old and new changes of the same project into training and testing.
- A clue that secretly contains the answer.

**How to split the data fairly:**

| Method | Meaning |
|---|---|
| By time | Train on older changes, test on newer ones |
| By project | Test on a project the model has never seen |

### 5.12 The comparison experiment

Compare different "detectives", each with different clues:

| System | Clues used |
|---|---|
| Baseline A | Code only |
| System B | Code + history |
| System C | Code + usage |
| System D | Code + settings |
| Full SEIR | Code + history + settings + usage |
| AI extension | Full SEIR + ML risk model |

### 5.13 Ablation study — the MOST important experiment

"Ablation" just means **add or remove one type of clue at a time and see what changes**. Like cooking: taste the soup, add salt, taste again, add pepper, taste again.

Order:
1. Code only
2. Code + history
3. Code + settings
4. Code + usage
5. Code + history + settings
6. Code + history + usage
7. Code + settings + usage
8. Everything

**Keep the test exactly the same each time** — only the clues change. If a clue type doesn't help, **I report that honestly**.

### 5.14 How we measure — the scores explained

| Score | Plain meaning | Example |
|---|---|---|
| **Precision** | Of everything I flagged, how much was right? | Found 10 settings mentions, 8 were real → 80% |
| **Recall** | Of everything real, how much did I find? | There were 12 real mentions, I found 8 → 67% |
| **F1** | One number combining precision and recall | — |
| **Accuracy** | Overall % of correct answers | — |
| **False positive** | A false alarm | Said "will break", it didn't |
| **False negative** | A miss | Said "safe", it broke (worse!) |
| **Confusion matrix** | A table showing which risk levels get mixed up | e.g. MEDIUM often mistaken for HIGH |
| **Calibration** | When it says "80% sure", is it right ~80% of the time? | — |
| **Coverage** | How much of the expected data I actually have | — |

### 5.15 Statistics — is the improvement real?

If adding a clue improves the score from 70% to 71%, that could be pure luck. So:
- Show a **range** ("between 68% and 74%") not just one number.
- Compare on the **same examples** for every system.
- If the dataset is small, **don't overclaim** — focus on explaining individual cases.

### 5.16 Error analysis — learning from mistakes

Don't just report the final score. Look at the **individual mistakes** and sort them:

- Missed a code connection
- Missed a settings mention / matched it to the wrong piece
- Usage missed because fake users didn't cover it
- History matched to the wrong piece
- Risk level wrong because clues were missing
- AI explanation forgot an important clue

For each: *why did it happen, and is it fixable or a fundamental limit?*

### 5.17 Checking the practice data before training

| Check | Question |
|---|---|
| Class balance | Are there enough LOW, MEDIUM **and** HIGH examples? |
| Project balance | Does one project take over the whole dataset? |
| Missing clues | Which clue types are missing most often? |
| Leakage | Does any clue reveal the answer? |
| Timing | Were all clues available before the change? |
| Duplicates | Are near-identical examples repeated? |
| Label consistency | Would similar cases get the same label? |

### 5.18 Checking the AI Explainer

The explanation is not judged by "does it sound nice?" — it's judged by **"is every sentence backed by a real clue?"**

Steps:
1. Give the AI a fixed set of clues.
2. List which clues it *should* mention.
3. Check which it *did* mention.
4. Check every sentence is supported by a clue.
5. Check it mentioned the uncertainties (e.g. "usage data is limited").
6. Count any made-up statements (**hallucinations**).
7. Ask people whether the suggested next step is useful.

| Score | Meaning |
|---|---|
| Evidence coverage | Important clues mentioned ÷ important clues available |
| Supported-claim rate | True sentences ÷ all sentences |
| Hallucination rate | Made-up sentences ÷ all sentences (**want this near 0**) |
| Uncertainty coverage | Did it mention what we're unsure about? |
| Usefulness | Did people find the advice helpful? |

**Comparison:** simple template (no AI) vs. AI without checks vs. AI with my clue-checker.

### 5.19 Honest limitations ("threats to validity")

Things that could make results less trustworthy — and I must mention them in the final report, not hide them:

| Problem | Why it matters | What I do about it |
|---|---|---|
| Only a few projects | Results may not apply to others | Use varied projects |
| Java only | May not apply to other languages | Say clearly "Java only" |
| Usage data is limited | "Not seen" ≠ "not used" | Record watch time and coverage |
| Labels are subjective | Different people might label differently | Write down labelling rules |
| Old history | Old code may not reflect today | Split data by time |
| Leakage | Fake-good results | Strict "before the change only" rule |
| Small dataset | Unstable results | Simple models, careful claims |
| Outside callers unseen | Hidden links missed | Mark as "possible / unknown" |

### 5.20 Result tables (to be filled in later)

My report has three empty tables to fill **with real measured numbers** — never invented ones:

- **Table A** — How accurate is each clue collector? (history, settings, usage)
- **Table B** — Code-only vs. code + each clue vs. full SEIR
- **Table C** — Types of mistakes, how many, why, fixable or not

### 5.21 Final checklist (before presenting)

I should be able to say **"yes"** to all of these:

- [ ] I can explain how a piece of code is matched to its history.
- [ ] Running my history counter twice gives the same numbers.
- [ ] I hand-checked a sample of history matches.
- [ ] I decided which settings file types are supported.
- [ ] I measured settings-reader precision/recall on a hand-checked sample.
- [ ] I record usage watch-time and coverage.
- [ ] I never treat "not seen" as "not used".
- [ ] Every clue has proof.
- [ ] My answer key is written down and separate from the clues.
- [ ] No future information leaks into the clues.
- [ ] Every comparison uses the same test examples.
- [ ] I ran the ablation experiment.
- [ ] I report precision, recall, F1, false alarms and misses.
- [ ] I looked at individual mistakes, not just averages.
- [ ] I clearly separate real results from made-up examples.
- [ ] The AI explanation can point back to real clues.

### My role in one sentence

> *"I collect and check history, settings and usage clues, turn them into reliable data with proof, and test whether these extra clues actually make SEIR's risk predictions better."*

---

## Part 6 — The tools I will use

My whole part is **one Python program** running as a small web service (the **"Evidence Service"**). The backend (Java) calls it through simple web requests.

```
  Backend (Member 2)  ──"analyze this project"──►  MY Evidence Service (Python)
                                                     1. History collector
                                                     2. Settings collector
                                                     3. Usage collector
                                                     4. Practice-data builder
                                                     5. AI Explainer
  Backend  ◄──────── clues + explanation (JSON) ─────
```

| Area | Tools | What for |
|---|---|---|
| Foundation | **Python, FastAPI, Pydantic, pytest, Docker, Git** | Language, web service, standard format, tests, packaging |
| History | **PyDriller, GitPython** | Read the change history, download projects |
| Settings | **ruamel.yaml, jproperties, lxml, regex** | Read .yml / .properties / .xml files, spot class names |
| Usage | **Spring PetClinic, OpenTelemetry Java Agent, Locust, Jaeger, Docker Compose** | Sample app, usage recorder, fake users, viewer, one-command start |
| Data & experiments | **pandas, Parquet, scikit-learn, scipy, matplotlib, Jupyter, Excel/Sheets** | Build tables, save data, experiments, statistics, charts, hand-checking |
| AI Explainer | **Claude / OpenAI API** (or **Ollama** for free), **Jinja2** | Write explanations, fill-in-the-blank fallback |

### Web addresses my service offers the backend

| Address | What it does |
|---|---|
| `POST /analyze` | Collect all clues for a project |
| `GET /evidence/{piece}` | All clues for one piece |
| `GET /history/{piece}` | History for the timeline chart |
| `POST /runtime/upload` | Accept a usage log file |
| `POST /explain` | Write the explanation |

### Folder plan

```
seir-evidence/
├── app/
│   ├── main.py              ← the web service
│   ├── schema.py            ← the standard clue format
│   ├── collectors/
│   │   ├── git_history.py   ← history clues
│   │   ├── config_files.py  ← settings clues
│   │   └── runtime_usage.py ← usage clues
│   ├── dataset/             ← practice data + answer key
│   └── explainer/           ← AI explainer + checker + template
├── runtime-lab/             ← PetClinic + OpenTelemetry + Locust setup
├── notebooks/               ← experiments & charts
├── tests/
└── requirements.txt
```

---

## Part 7 — My step-by-step plan

| Step | What I do | Result |
|---|---|---|
| **1** | Agree with the team: *one piece = one Java class*, and the standard clue format | Shared rules |
| **2** | Pick projects (PetClinic + 3–5 Java projects) | Project list |
| **3** | Build the **history collector** (easiest, start here) | History clues + hand-check score |
| **4** | Build **practice data v1** (history only) → **give to Member 3 early** | First dataset |
| **5** | Build the **settings collector** + hand-check ~50 mentions | Settings clues + score |
| **6** | Set up **PetClinic + recorder + fake users** → usage collector | Usage clues + score |
| **7** | Build the **Explainer**: template first → AI → clue-checker | Explanation feature |
| **8** | Run **experiments** with Member 3 (ablation, explanation tests) | Filled Tables A, B, C |

**In one line:**
> Collect history → build practice data and hand it over → add settings clues → add usage clues → build the Explainer → run the experiments → report honestly.

---

## Quick glossary

| Word | Simple meaning |
|---|---|
| Component | One piece of code (for us: one Java class) |
| Git / commit | The project's history / one saved change |
| Config | Settings files |
| Runtime | While the program is running |
| Evidence / clue | A fact about a piece of code |
| Provenance | Proof of where a clue came from |
| Ground truth / label | The correct answer (answer key) |
| Feature | A clue turned into a number for the model |
| Leakage | Accidentally using future information (cheating) |
| Ablation | Adding/removing one clue type at a time to see if it helps |
| Hallucination | When the AI makes something up |
| Blast radius | Everything that might break from one change |
| Baseline | The simple version we compare against |

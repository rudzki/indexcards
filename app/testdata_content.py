TEST_EMAIL_DOMAIN = '@test.indexcards.invalid'

TEST_CUSTOM_CSS = """\
/* test data: custom CSS injection demo */
.site-footer { border-top-width: 3px; }
"""

TEST_CUSTOM_HEAD_HTML = """\
<!-- test data: custom head HTML injection demo -->
<meta name="x-indexcards-test" content="1">
"""

TEST_CUSTOM_FOOTER_HTML = """\
<!-- test data: custom footer HTML injection demo -->
<!-- analytics or chat widgets would go here, e.g.:
<script async src="https://www.googletagmanager.com/gtag/js?id=G-XXXXXXXX"></script>
-->
"""

TEST_USERS = [
    {'email': f'editor-maria{TEST_EMAIL_DOMAIN}', 'display_name': 'Maria Chen', 'role': 'editor', 'days_ago': 40},
    {'email': f'author-james{TEST_EMAIL_DOMAIN}', 'display_name': 'James Okafor', 'role': 'author', 'days_ago': 30},
    {'email': f'author-lena{TEST_EMAIL_DOMAIN}', 'display_name': 'Lena Björk', 'role': 'author', 'days_ago': 20},
]

TEST_ENTRIES = [
    {
        'title': 'Sourdough',
        'summary': 'A bread made by the fermentation of dough using wild lactobacilli and yeast.',
        'aliases': ['Sourdough Bread', 'Levain'],
        'author_index': 0,
        'body': (
            '**Sourdough** is one of the oldest forms of grain fermentation, dating back to '
            'ancient Egypt around 1500 BCE. Unlike commercial bread that uses cultivated yeast, '
            'sourdough relies on a [starter](/sourdough-starter/) — a symbiotic culture of wild '
            'yeast and lactic acid bacteria.\n\n'
            '## The Science\n\n'
            'Sourdough fermentation is a complex biochemical process. The lactic acid bacteria '
            '(primarily *Lactobacillus*) produce lactic and acetic acids, which give the bread '
            'its characteristic tang. The wild yeast (often *Saccharomyces* species) produces '
            'CO₂ for leavening.\n\n'
            'The low pH environment created by the acids has several effects:\n\n'
            '- **Flavor development** — the acids themselves contribute flavor, but they also '
            'promote enzymatic activity that breaks down proteins and starches into flavorful compounds\n'
            '- **Improved keeping quality** — the acidic environment inhibits mold growth, giving '
            'sourdough a longer shelf life than commercial bread\n'
            '- **Digestibility** — fermentation partially breaks down gluten and phytic acid, '
            'which may make sourdough easier to digest for some people[^phytic]\n'
            '- **Nutrient availability** — phytic acid reduction increases the bioavailability '
            'of minerals like iron, zinc, and magnesium\n\n'
            '## Basic Method\n\n'
            '1. **Mix** — combine flour, water, salt, and active [starter](/sourdough-starter/) '
            '(typically 15–20% of flour weight)\n'
            '2. **Bulk fermentation** — let the dough rise at room temperature for 4–12 hours, '
            'performing stretch-and-folds every 30–60 minutes during the first 2 hours\n'
            '3. **Shape** — pre-shape into a round, rest 20 minutes, then final shape into a '
            'batard or boule\n'
            '4. **Proof** — cold-proof in the refrigerator for 8–16 hours (retarding develops '
            'flavor and makes the dough easier to score)\n'
            '5. **Bake** — score the top, bake in a preheated Dutch oven at 250°C / 480°F with '
            'the lid on for 20 minutes, then lid off at 230°C / 450°F for 20–25 minutes\n\n'
            '## Hydration\n\n'
            'The ratio of water to flour (by weight) is called *hydration*. Beginner-friendly '
            'doughs are around 65–70%. Higher hydrations (75–85%) produce a more open crumb with '
            'larger, irregular holes, but the dough is much harder to handle.\n\n'
            '## Flour Choices\n\n'
            'Strong bread flour (high protein, 12–14%) gives the best gluten structure. Mixing '
            'in whole wheat, rye, or spelt adds flavor and nutritional complexity at the cost of '
            'a denser crumb. [Rye](/rye/) flour in particular ferments aggressively and is '
            'traditionally used in many European sourdough traditions.\n\n'
            '## Cultural Significance\n\n'
            'San Francisco sourdough became iconic during the California Gold Rush, when miners '
            'carried starters with them. The unique local bacteria (*Lactobacillus sanfranciscensis*) '
            'was named after the city. Today, sourdough has seen a global revival, driven partly by '
            'the [fermentation](/fermentation/) movement and partly by the COVID-19 pandemic, when '
            'home baking surged worldwide.\n\n'
            '[^phytic]: Phytic acid binds to minerals in grain, reducing absorption. Sourdough '
            'fermentation breaks it down more effectively than commercial yeast fermentation.'
        ),
        'published_days_ago': 60,
        'edits': [
            {'changelog': None, 'days_ago': 60},
            {'changelog': 'Added hydration and flour sections', 'days_ago': 45},
            {'changelog': 'Added cultural significance', 'days_ago': 20},
            {'changelog': 'Added footnote on phytic acid', 'days_ago': 5},
        ],
    },
    {
        'title': 'Sourdough Starter',
        'summary': 'A fermented mixture of flour and water that contains wild yeast and bacteria for leavening bread.',
        'aliases': ['Mother Dough', 'Starter Culture'],
        'author_index': 0,
        'body': (
            'A **sourdough starter** is a live culture of wild yeast and lactic acid bacteria '
            'maintained by regular feedings of flour and water. It serves as the leavening agent '
            'for [sourdough](/sourdough/) bread.\n\n'
            '## Creating a Starter\n\n'
            'A new starter can be created from scratch in 5–14 days:\n\n'
            '1. **Day 1** — mix equal parts flour and water (by weight), ~50g each. Cover loosely.\n'
            '2. **Days 2–5** — discard half, feed with fresh flour and water daily. The mixture '
            'will smell unpleasant at first (bad bacteria dominating) before settling into a '
            'pleasant, yeasty aroma.\n'
            '3. **Days 5–14** — continue daily feedings. The starter is ready when it reliably '
            'doubles in volume within 4–8 hours of feeding.\n\n'
            'Whole grain flour (especially rye) accelerates the process because the bran carries '
            'more wild yeast and bacteria.\n\n'
            '## Maintenance\n\n'
            'An active starter needs regular feeding. Two approaches:\n\n'
            '- **Room temperature** — feed once or twice daily. Best for frequent bakers.\n'
            '- **Refrigerated** — feed once a week. The cold slows fermentation. Take it out '
            'and feed 1–2 times before baking to reactivate.\n\n'
            '## The Float Test\n\n'
            'Drop a spoonful of starter into water. If it floats, it has enough gas to leaven '
            'bread. This isn\'t foolproof — some high-hydration starters float even when spent — '
            'but it\'s a useful quick check.\n\n'
            '## Troubleshooting\n\n'
            '- **Hooch** (dark liquid on top) — the starter is hungry. Pour it off and feed.\n'
            '- **Not rising** — try a warmer spot (25–28°C is ideal), use whole grain flour, '
            'or switch to filtered water (chlorine can inhibit fermentation).\n'
            '- **Smells like acetone** — overly acidic, needs more frequent feeding.\n\n'
            'A healthy starter can last indefinitely. Some bakeries maintain starters that are '
            'over a century old.'
        ),
        'published_days_ago': 55,
        'edits': [
            {'changelog': None, 'days_ago': 55},
            {'changelog': 'Added troubleshooting section', 'days_ago': 30},
        ],
    },
    {
        'title': 'Fermentation',
        'summary': 'A metabolic process in which organisms convert carbohydrates into alcohol or acids.',
        'aliases': [],
        'author_index': 1,
        'body': (
            '**Fermentation** is a metabolic process in which microorganisms — yeast, bacteria, '
            'or molds — convert sugars and starches into other compounds, typically alcohol, '
            'acids, or gases.\n\n'
            '## Types\n\n'
            '### Alcoholic Fermentation\n\n'
            'Yeast converts sugars into ethanol and CO₂. This is the basis for beer, wine, '
            'spirits, and the rise in bread dough.\n\n'
            '### Lactic Acid Fermentation\n\n'
            'Bacteria convert sugars into lactic acid. This produces yogurt, sauerkraut, kimchi, '
            'and the tang in [sourdough](/sourdough/). There are two sub-types:\n\n'
            '- **Homofermentative** — produces mainly lactic acid (milder flavor)\n'
            '- **Heterofermentative** — produces lactic acid, acetic acid, ethanol, and CO₂ '
            '(more complex flavor)\n\n'
            '### Acetic Acid Fermentation\n\n'
            'Bacteria convert ethanol into acetic acid — this is how vinegar is made.\n\n'
            '## Fermented Foods Around the World\n\n'
            '| Food | Region | Fermentation Type |\n'
            '|------|--------|-------------------|\n'
            '| Kimchi | Korea | Lactic acid |\n'
            '| Miso | Japan | Mold + lactic acid |\n'
            '| Sauerkraut | Germany | Lactic acid |\n'
            '| Tempeh | Indonesia | Mold |\n'
            '| Kefir | Caucasus | Lactic acid + alcoholic |\n'
            '| Injera | Ethiopia | Lactic acid |\n'
            '| Kvass | Russia | Alcoholic + lactic acid |\n\n'
            '## Health Benefits\n\n'
            'Fermented foods are a significant source of probiotics — live microorganisms that '
            'may benefit gut health. The fermentation process also increases vitamin content '
            '(especially B vitamins), breaks down anti-nutrients like phytic acid, and can '
            'preserve food for months or years without refrigeration.\n\n'
            '## Industrial Applications\n\n'
            'Beyond food, fermentation is used to produce antibiotics (penicillin), biofuels '
            '(ethanol from corn), amino acids (MSG), and organic acids (citric acid). '
            'Modern biotechnology relies heavily on engineered fermentation.'
        ),
        'published_days_ago': 48,
        'edits': [
            {'changelog': None, 'days_ago': 48},
            {'changelog': 'Added world foods table', 'days_ago': 25},
            {'changelog': 'Added industrial applications', 'days_ago': 10},
        ],
    },
    {
        'title': 'The Silk Road',
        'summary': 'An ancient network of trade routes connecting East Asia to the Mediterranean.',
        'aliases': ['Silk Routes'],
        'author_index': 1,
        'body': (
            '**The Silk Road** was a network of trade routes that connected China and East Asia '
            'to the Mediterranean world, active from roughly the 2nd century BCE to the 15th '
            'century CE. Despite the name (coined by German geographer Ferdinand von Richthofen '
            'in 1877), silk was only one of many goods traded.\n\n'
            '## Routes\n\n'
            'The Silk Road was not a single path but a web of overland and maritime routes:\n\n'
            '- **Northern route** — through Central Asia, north of the Taklamakan Desert, '
            'via Samarkand and Bukhara to the Black Sea\n'
            '- **Southern route** — south of the Taklamakan, through the Karakoram Mountains '
            'to Persia and the Levant\n'
            '- **Maritime route** — by sea from Chinese ports through the Strait of Malacca, '
            'across the Indian Ocean, to the Red Sea and East Africa\n\n'
            '## What Was Traded\n\n'
            '**Eastward:** gold, silver, wool, linen, glass, wine, horses\n\n'
            '**Westward:** silk, porcelain, tea, spices, paper, gunpowder, compass technology\n\n'
            'But goods were rarely carried the full distance by a single merchant. Instead, '
            'items passed through many hands at trading posts and [caravanserais](/caravanserai/), '
            'with each intermediary adding markup.\n\n'
            '## Cultural Exchange\n\n'
            'The Silk Road\'s most lasting impact was cultural, not commercial:\n\n'
            '- **Religion** — Buddhism spread from India to China and Central Asia. Islam '
            'expanded eastward. Christianity (Nestorian) reached China.\n'
            '- **Technology** — paper-making spread westward from China (2nd century), reaching '
            'the Islamic world by the 8th century and Europe by the 12th. Printing, gunpowder, '
            'and the compass followed similar paths.\n'
            '- **Art and architecture** — Greco-Buddhist art in Gandhara blended Hellenistic '
            'and Indian aesthetics. [Islamic geometric patterns](/islamic-geometry/) influenced '
            'design across the entire route.\n'
            '- **Language** — trade pidgins developed, and loanwords traveled with goods\n'
            '- **Science** — astronomical, mathematical, and medical knowledge flowed in both '
            'directions. The Indian numeral system reached the Arab world and then Europe.\n\n'
            '## Disease\n\n'
            'The Silk Road also transmitted disease. The Black Death (bubonic plague) likely '
            'traveled from Central Asia to Europe via Silk Road trade routes in the 1340s, '
            'killing an estimated 30–60% of Europe\'s population.\n\n'
            '## Decline\n\n'
            'The overland Silk Road declined for several reasons:\n\n'
            '- The fall of the Mongol Empire fragmented the political stability that had '
            'facilitated cross-continental trade\n'
            '- The Ottoman Empire\'s control of key routes raised costs for European merchants\n'
            '- European maritime exploration (15th–16th centuries) established sea routes to '
            'Asia that were faster and could carry more cargo\n\n'
            'The concept was revived in 2013 when China launched the Belt and Road Initiative, '
            'a modern infrastructure and trade network consciously evoking the historical routes.'
        ),
        'published_days_ago': 52,
        'edits': [
            {'changelog': None, 'days_ago': 52},
            {'changelog': 'Added disease section', 'days_ago': 35},
            {'changelog': 'Expanded cultural exchange section', 'days_ago': 18},
            {'changelog': 'Added decline section and BRI note', 'days_ago': 8},
        ],
    },
    {
        'title': 'Counterpoint',
        'summary': 'The art of combining independent melodic lines in a musical composition.',
        'aliases': ['Contrapuntal Music'],
        'author_index': 2,
        'body': (
            '**Counterpoint** is a technique of musical composition in which two or more '
            'independent melodic lines (voices) are combined according to a set of rules. '
            'The word comes from the Latin *punctus contra punctum* — "point against point" '
            'or "note against note."\n\n'
            '## Species Counterpoint\n\n'
            'The pedagogical tradition, codified by Johann Joseph Fux in *Gradus ad Parnassum* '
            '(1725), teaches counterpoint in five progressive species:\n\n'
            '1. **First species** — note against note. Each voice moves in whole notes.\n'
            '2. **Second species** — two notes against one. Introduces passing tones.\n'
            '3. **Third species** — four notes against one. Greater melodic freedom.\n'
            '4. **Fourth species** — syncopation. Suspensions and resolutions create tension.\n'
            '5. **Fifth species** — florid counterpoint. Combines all previous species freely.\n\n'
            '## Rules and Guidelines\n\n'
            'Classical counterpoint follows strict voice-leading rules:\n\n'
            '- **Contrary motion** is preferred — when one voice rises, the other falls\n'
            '- **Parallel fifths and octaves** are forbidden — they reduce the independence '
            'of the voices\n'
            '- **Voice crossing** is avoided — each voice should stay in its own range\n'
            '- **Dissonances** must be prepared and resolved — they create tension that '
            'resolves to consonance\n\n'
            '## Bach and the Fugue\n\n'
            'Johann Sebastian Bach is considered the supreme master of counterpoint. His '
            '*Well-Tempered Clavier* contains 48 preludes and fugues exploring every major '
            'and minor key. The [fugue](/fugue/) — a form in which a subject is introduced by '
            'one voice and then imitated by others — is the pinnacle of contrapuntal writing.\n\n'
            'Bach\'s *Art of Fugue* and *Musical Offering* push counterpoint to extraordinary '
            'complexity, including canons that work in retrograde (played backwards), '
            'inversion (flipped upside down), and augmentation (stretched in time).\n\n'
            '## Beyond Classical Music\n\n'
            'Contrapuntal thinking appears in many genres:\n\n'
            '- **Jazz** — improvised counterpoint between soloists and rhythm section\n'
            '- **Progressive rock** — bands like Yes and King Crimson use interlocking '
            'melodic lines\n'
            '- **Film scoring** — John Williams frequently layers multiple themes contrapuntally\n'
            '- **Electronic music** — polyrhythmic layering in artists like Aphex Twin\n\n'
            'The principles of counterpoint — independence of voices, tension and resolution, '
            'structural balance — remain foundational to musical composition across traditions.'
        ),
        'published_days_ago': 38,
        'edits': [
            {'changelog': None, 'days_ago': 38},
            {'changelog': 'Added species counterpoint breakdown', 'days_ago': 22},
            {'changelog': 'Added non-classical examples', 'days_ago': 7},
        ],
    },
    {
        'title': 'Fugue',
        'summary': 'A contrapuntal composition in which a short melody (subject) is introduced and developed through imitation.',
        'aliases': [],
        'author_index': 2,
        'body': (
            'A **fugue** is a musical form built on the systematic imitation of a short theme '
            '(the *subject*) across multiple voices. It represents the most sophisticated '
            'application of [counterpoint](/counterpoint/).\n\n'
            '## Structure\n\n'
            '### Exposition\n\n'
            'The subject enters in one voice alone. A second voice enters with the subject '
            '(usually transposed to the dominant key), while the first voice continues with '
            'a *countersubject* — a complementary melody designed to work against the subject. '
            'Additional voices enter in turn.\n\n'
            '### Development\n\n'
            'After all voices have stated the subject, the fugue develops freely. The composer '
            'may use:\n\n'
            '- **Stretto** — overlapping entries of the subject before the previous one finishes\n'
            '- **Inversion** — the subject played upside down (intervals reversed)\n'
            '- **Augmentation** — the subject in longer note values (slower)\n'
            '- **Diminution** — the subject in shorter note values (faster)\n'
            '- **Episodes** — passages that don\'t state the full subject, often modulating '
            'to new keys using fragments of the subject or countersubject\n\n'
            '### Final Section\n\n'
            'The fugue typically returns to the home key for a final statement of the subject, '
            'sometimes over a pedal point (sustained bass note).\n\n'
            '## Notable Fugues\n\n'
            '- Bach, *Well-Tempered Clavier* — 48 fugues in all keys, the definitive collection\n'
            '- Bach, *Art of Fugue* — a cycle exploring a single subject in increasingly '
            'complex ways, left unfinished at his death\n'
            '- Beethoven, *Grosse Fuge* Op. 133 — a violent, modern-sounding fugue that '
            'shocked contemporary audiences\n'
            '- Shostakovich, *24 Preludes and Fugues* — a 20th-century response to Bach'
        ),
        'published_days_ago': 35,
        'edits': [
            {'changelog': None, 'days_ago': 35},
            {'changelog': 'Added notable fugues list', 'days_ago': 15},
        ],
    },
    {
        'title': 'Plate Tectonics',
        'summary': 'The scientific theory that Earth\'s outer shell is divided into plates that float on the mantle.',
        'aliases': ['Continental Drift', 'Tectonic Plates'],
        'author_index': 1,
        'body': (
            '**Plate tectonics** is the unifying theory of geology. It explains earthquakes, '
            'volcanic eruptions, mountain building, and the shape of continents through the '
            'movement of rigid lithospheric plates over the semi-fluid asthenosphere.\n\n'
            '## The Plates\n\n'
            'Earth\'s lithosphere is broken into about 15 major plates and several minor ones. '
            'The largest include:\n\n'
            '- **Pacific Plate** — the largest, almost entirely oceanic\n'
            '- **North American Plate** — includes most of North America and the western Atlantic\n'
            '- **Eurasian Plate** — Europe and most of Asia\n'
            '- **African Plate** — Africa and surrounding ocean floor\n'
            '- **Antarctic Plate** — Antarctica and surrounding ocean\n\n'
            '## Plate Boundaries\n\n'
            '### Divergent Boundaries\n\n'
            'Plates move apart. Magma rises to fill the gap, creating new crust. The Mid-Atlantic '
            'Ridge is the most famous example — Iceland sits directly on it, which is why it has '
            'so much volcanic activity.\n\n'
            '### Convergent Boundaries\n\n'
            'Plates collide. Three scenarios:\n\n'
            '- **Ocean-ocean** — one plate subducts (dives beneath the other), creating deep '
            'trenches and volcanic island arcs (e.g., Japan, Philippines)\n'
            '- **Ocean-continent** — the denser oceanic plate subducts, creating coastal '
            'mountains and volcanoes (e.g., the Andes)\n'
            '- **Continent-continent** — neither plate subducts easily; instead they crumple '
            'upward into massive mountain ranges (e.g., the [Himalayas](/himalayas/))\n\n'
            '### Transform Boundaries\n\n'
            'Plates slide past each other horizontally. The San Andreas Fault in California '
            'is the most famous transform boundary.\n\n'
            '## Driving Forces\n\n'
            'What moves the plates? The primary mechanism is **mantle convection** — heat from '
            'Earth\'s core drives slow circulation in the mantle. Other contributing forces:\n\n'
            '- **Ridge push** — elevated mid-ocean ridges push plates apart by gravity\n'
            '- **Slab pull** — the weight of subducting plates pulls the rest of the plate along\n\n'
            '## Evidence\n\n'
            'The theory rests on multiple lines of evidence:\n\n'
            '- Continent shapes fit together like puzzle pieces (first noted by Alfred Wegener)\n'
            '- Matching fossil and rock sequences on continents now separated by oceans\n'
            '- Symmetric magnetic striping on the ocean floor around mid-ocean ridges\n'
            '- GPS measurements showing plates moving 1–15 cm/year\n'
            '- The distribution of earthquakes and volcanoes along plate boundaries\n\n'
            '## Historical Note\n\n'
            'Alfred Wegener proposed continental drift in 1912 but couldn\'t explain the '
            'mechanism. He was ridiculed by the geological establishment. It wasn\'t until '
            'the 1960s that seafloor spreading and magnetic evidence vindicated his core idea, '
            'leading to the modern theory of plate tectonics.'
        ),
        'published_days_ago': 44,
        'edits': [
            {'changelog': None, 'days_ago': 44},
            {'changelog': 'Expanded convergent boundaries', 'days_ago': 28},
            {'changelog': 'Added evidence section', 'days_ago': 14},
            {'changelog': 'Added Wegener historical note', 'days_ago': 3},
        ],
    },
    {
        'title': 'Algorithm',
        'summary': 'A step-by-step procedure for solving a problem or accomplishing a task.',
        'aliases': ['Algorithms'],
        'author_index': None,
        'body': (
            'An **algorithm** is a finite sequence of well-defined instructions used to solve a '
            'class of problems or to perform a computation.\n\n'
            '## Properties\n\n'
            'A well-formed algorithm has several key properties:\n\n'
            '- **Finiteness** — it terminates after a finite number of steps\n'
            '- **Definiteness** — each step is precisely defined\n'
            '- **Input** — it accepts zero or more inputs\n'
            '- **Output** — it produces at least one output\n'
            '- **Effectiveness** — each step is basic enough to be carried out\n\n'
            '## Complexity\n\n'
            'The efficiency of an algorithm is typically measured in terms of how its runtime '
            'and memory usage grow with input size. The most common framework for this is '
            'asymptotic notation — O(1) for constant time, O(log n) for logarithmic, O(n) '
            'for linear, and so on.\n\n'
            '## Historical Roots\n\n'
            'The word *algorithm* derives from the name of the 9th-century Persian mathematician '
            'al-Khwarizmi, whose work on arithmetic with Hindu-Arabic numerals was translated '
            'into Latin as *Algoritmi de numero Indorum*. But the concept is far older — '
            'Euclid\'s algorithm for finding the greatest common divisor dates to around 300 BCE '
            'and is still used today.\n\n'
            '## Examples\n\n'
            'Well-known algorithms include binary search, quicksort, Dijkstra\'s shortest path, '
            'and the [Fast Fourier Transform](/fast-fourier-transform/). The field of '
            '[machine learning](/machine-learning/) is built on algorithms that learn patterns '
            'from data.\n\n'
            '## Undecidability\n\n'
            'Not every problem has an algorithmic solution. Alan Turing proved in 1936 that the '
            '[halting problem](/the-halting-problem/) — determining whether an arbitrary program '
            'will ever stop running — is undecidable. This established fundamental limits on '
            'what computation can achieve.'
        ),
        'published_days_ago': 65,
        'edits': [
            {'changelog': None, 'days_ago': 65},
            {'changelog': 'Added historical roots', 'days_ago': 40},
            {'changelog': 'Added undecidability section', 'days_ago': 12},
        ],
    },
    {
        'title': 'The Halting Problem',
        'summary': 'The undecidable problem of determining whether an arbitrary program will terminate.',
        'aliases': ['Halting Problem'],
        'author_index': None,
        'body': (
            '**The Halting Problem** asks: given a description of an arbitrary program and '
            'an input, determine whether the program will eventually halt (finish running) '
            'or continue to run forever.\n\n'
            '## Undecidability\n\n'
            'Alan Turing proved in 1936 that no general [algorithm](/algorithm/) can solve '
            'the halting problem for all possible program-input pairs. This was one of the '
            'first problems proven to be *undecidable*.\n\n'
            '## The Proof (Sketch)\n\n'
            'The proof uses a diagonal argument:\n\n'
            '1. Assume a halting oracle H(P, I) exists that returns true if program P halts on input I\n'
            '2. Construct a program D that, given P, runs H(P, P) and does the opposite\n'
            '3. Ask: does D halt on input D?\n'
            '4. Either answer leads to a contradiction\n\n'
            'This self-referential structure is reminiscent of the liar\'s paradox ("this statement '
            'is false") and Gödel\'s incompleteness theorems.\n\n'
            '## Implications\n\n'
            'The halting problem establishes fundamental limits on what can be computed. '
            'Many practical problems are equivalent to or harder than the halting problem:\n\n'
            '- Can this program ever reach a particular line of code? (Undecidable)\n'
            '- Does this program have a security vulnerability? (Undecidable in general)\n'
            '- Are these two programs equivalent? (Undecidable — Rice\'s theorem)\n\n'
            'This doesn\'t mean these questions are *never* answerable — just that no single '
            'algorithm can answer them for *all* possible inputs. In practice, static analysis '
            'tools and [formal verification](/formal-verification/) work well for specific, '
            'constrained cases.'
        ),
        'published_days_ago': 58,
        'edits': [
            {'changelog': None, 'days_ago': 58},
            {'changelog': 'Added practical implications', 'days_ago': 20},
        ],
    },
    {
        'title': 'Machine Learning',
        'summary': 'A subfield of AI where systems learn patterns from data rather than being explicitly programmed.',
        'aliases': ['ML', 'Statistical Learning'],
        'author_index': 0,
        'body': (
            '**Machine learning** is a branch of artificial intelligence focused on building '
            'systems that improve their performance on a task through experience (data) rather '
            'than explicit programming.\n\n'
            '## Paradigms\n\n'
            '### Supervised Learning\n\n'
            'The model learns from labeled examples — input-output pairs. Given enough examples, '
            'it learns to predict outputs for new inputs. This covers:\n\n'
            '- **Classification** — predicting a category (spam/not spam, cat/dog, benign/malignant)\n'
            '- **Regression** — predicting a continuous value (house price, temperature, stock return)\n\n'
            'Common [algorithms](/algorithm/): linear regression, decision trees, random forests, '
            'support vector machines, neural networks.\n\n'
            '### Unsupervised Learning\n\n'
            'The model finds structure in unlabeled data:\n\n'
            '- **Clustering** — grouping similar items (k-means, DBSCAN, hierarchical)\n'
            '- **Dimensionality reduction** — compressing high-dimensional data into fewer '
            'dimensions while preserving structure (PCA, t-SNE, UMAP)\n'
            '- **Anomaly detection** — identifying unusual data points\n\n'
            '### Reinforcement Learning\n\n'
            'An agent learns by interacting with an environment, receiving rewards or '
            'penalties for its actions. It balances *exploration* (trying new actions) with '
            '*exploitation* (repeating rewarded actions). Notable successes include AlphaGo '
            'and robotic control.\n\n'
            '## The Bias-Variance Tradeoff\n\n'
            'A fundamental tension: simple models underfit (high bias, low variance), '
            'complex models overfit (low bias, high variance). The goal is the sweet spot '
            'where the model captures real patterns without memorizing noise.\n\n'
            'Techniques for managing this tradeoff:\n\n'
            '- **Regularization** — penalizes model complexity (L1/L2, dropout)\n'
            '- **Cross-validation** — evaluates on held-out data to detect overfitting\n'
            '- **Ensemble methods** — combine multiple models (bagging, boosting)\n\n'
            '## Deep Learning\n\n'
            'A subset of ML using neural networks with many layers. Dominant in:\n\n'
            '- **Computer vision** — convolutional neural networks (CNNs)\n'
            '- **Natural language processing** — transformers (GPT, BERT)\n'
            '- **Speech recognition** — recurrent networks, transformers\n'
            '- **Generative AI** — diffusion models, large language models\n\n'
            '## Ethical Considerations\n\n'
            'ML systems can inherit and amplify biases present in training data. They can be '
            'opaque (the "black box" problem), making it hard to understand or challenge their '
            'decisions. Responsible deployment requires careful attention to fairness, '
            'transparency, and accountability.'
        ),
        'published_days_ago': 30,
        'edits': [
            {'changelog': None, 'days_ago': 30},
            {'changelog': 'Added deep learning section', 'days_ago': 15},
            {'changelog': 'Added ethics section', 'days_ago': 5},
        ],
    },
    {
        'title': 'Fast Fourier Transform',
        'summary': 'An efficient algorithm for computing the discrete Fourier transform.',
        'aliases': ['FFT'],
        'author_index': None,
        'body': (
            'The **Fast Fourier Transform** is an [algorithm](/algorithm/) that computes the '
            'discrete Fourier transform (DFT) of a sequence in O(n log n) time, compared to '
            'O(n²) for the naive approach.\n\n'
            '## Applications\n\n'
            '- **Signal processing** — filtering, spectral analysis\n'
            '- **Image processing** — compression (JPEG uses a related transform)\n'
            '- **Audio** — equalization, pitch detection, noise reduction\n'
            '- **Polynomial multiplication** — multiply two polynomials in O(n log n)\n'
            '- **Large integer multiplication** — the Schönhage-Strassen algorithm\n'
            '- **Solving differential equations** — spectral methods\n\n'
            '## The Cooley-Tukey Algorithm\n\n'
            'The most common FFT variant, published in 1965 by James Cooley and John Tukey. '
            'It recursively breaks the DFT into smaller DFTs, exploiting symmetry and '
            'periodicity of the complex roots of unity.\n\n'
            '## Historical Note\n\n'
            'Though credited to Cooley and Tukey, Gauss described an essentially identical '
            'method in 1805 — predating even the formal definition of the Fourier transform. '
            'His work remained unpublished and was rediscovered only in the 20th century.'
        ),
        'published_days_ago': 50,
        'edits': [
            {'changelog': None, 'days_ago': 50},
        ],
    },
    {
        'title': 'Wabi-Sabi',
        'summary': 'A Japanese aesthetic centered on the acceptance of transience and imperfection.',
        'aliases': [],
        'author_index': 2,
        'body': (
            '**Wabi-sabi** (侘寂) is a Japanese aesthetic and worldview rooted in the acceptance '
            'of imperfection, impermanence, and incompleteness. It finds beauty in things that '
            'are modest, humble, and unconventional.\n\n'
            '## Origins\n\n'
            'Wabi-sabi has roots in Zen Buddhism and the tea ceremony tradition. The tea master '
            'Sen no Rikyū (1522–1591) was instrumental in elevating the aesthetic, favoring '
            'simple, rustic tea bowls over ornate Chinese imports. He taught that beauty lies '
            'in austerity, directness, and the intimate.\n\n'
            '## Wabi and Sabi\n\n'
            'The two words originally had distinct meanings:\n\n'
            '- **Wabi** (侘) — originally meant the loneliness of living in nature, far from '
            'society. Over time it evolved to mean rustic simplicity, understated elegance, and '
            'quietness. A wabi object is simple without being crude.\n'
            '- **Sabi** (寂) — originally meant "chill" or "lean." It evolved to convey the '
            'beauty of aging and wear — the patina on old wood, the moss on a stone, the crack '
            'in a glaze. A sabi object shows its age honestly.\n\n'
            'Together they describe a sensitivity to beauty that is imperfect, impermanent, '
            'and incomplete.\n\n'
            '## Principles\n\n'
            '- Nothing lasts — impermanence is fundamental, not something to resist\n'
            '- Nothing is finished — there is always room for growth and change\n'
            '- Nothing is perfect — flaws and irregularities are features, not defects\n\n'
            '## Examples\n\n'
            '- **Kintsugi** — repairing broken pottery with gold lacquer, making the cracks '
            'a visible part of the object\'s history rather than something to hide\n'
            '- **Tea ceremony** — the deliberate use of imperfect, handmade utensils in a '
            'carefully choreographed but unhurried ritual\n'
            '- **Japanese gardens** — designed to evoke natural landscapes rather than '
            'impose geometric order. Moss, weathered stone, and asymmetry are prized.\n'
            '- **Haiku** — the poetic form captures a fleeting moment in nature with economy '
            'and restraint\n\n'
            '## Contrast with Western Aesthetics\n\n'
            'Western aesthetics have historically prized symmetry, permanence, grandeur, and '
            'technical perfection (think Greek temples, Renaissance painting, Versailles). '
            'Wabi-sabi inverts these values. Where Western tradition might see decay, wabi-sabi '
            'sees the passage of time made visible. Where Western design aims for completion, '
            'wabi-sabi embraces the ongoing and the unfinished.\n\n'
            'This contrast is not absolute — the Arts and Crafts movement, brutalism, and '
            'contemporary design increasingly incorporate wabi-sabi principles.'
        ),
        'published_days_ago': 25,
        'edits': [
            {'changelog': None, 'days_ago': 25},
            {'changelog': 'Added contrast with Western aesthetics', 'days_ago': 12},
        ],
    },
    {
        'title': 'Mycelium',
        'summary': 'The vegetative, thread-like network that forms the main body of a fungus.',
        'aliases': ['Mycelia', 'Fungal Network'],
        'author_index': 1,
        'body': (
            '**Mycelium** is the vegetative body of a fungus — a branching network of thread-like '
            'cells called *hyphae* that permeates soil, wood, and other substrates. The mushroom '
            'is just the fruiting body; the mycelium is the organism.\n\n'
            '## Structure\n\n'
            'Individual hyphae are typically 2–10 micrometers in diameter, but a single mycelial '
            'network can extend for kilometers. The largest known organism on Earth is a honey '
            'fungus (*Armillaria ostoyae*) mycelium in Oregon\'s Blue Mountains, spanning roughly '
            '9.6 square kilometers and estimated to be 2,400–8,650 years old.\n\n'
            '## Ecological Roles\n\n'
            '### Decomposition\n\n'
            'Saprophytic fungi break down dead organic matter — fallen trees, leaf litter, animal '
            'remains — recycling nutrients back into the ecosystem. Without fungal decomposition, '
            'dead plant material would accumulate indefinitely.\n\n'
            '### Mycorrhizal Networks\n\n'
            'Most land plants form symbiotic relationships with mycorrhizal fungi. The mycelium '
            'extends far beyond the plant\'s root zone, dramatically increasing the plant\'s '
            'access to water and nutrients (especially phosphorus). In return, the plant provides '
            'the fungus with sugars from photosynthesis.\n\n'
            'These networks connect multiple plants, enabling resource sharing between them — '
            'sometimes called the "Wood Wide Web." Trees can transfer carbon, nutrients, and '
            'even chemical warning signals to neighbors through shared mycorrhizal networks.\n\n'
            '### Soil Structure\n\n'
            'Mycelium physically binds soil particles together, improving structure, water '
            'retention, and erosion resistance. Healthy soil is rich in fungal networks.\n\n'
            '## Applications\n\n'
            '- **Bioremediation** — certain fungi can break down pollutants including petroleum, '
            'pesticides, and heavy metals (mycoremediation)\n'
            '- **Materials** — mycelium can be grown into packaging, insulation, leather '
            'alternatives, and building materials. Companies like Ecovative grow mycelium '
            'composites as replacements for polystyrene foam.\n'
            '- **Food** — mycelium-based proteins are being developed as meat alternatives\n'
            '- **Medicine** — many antibiotics and immunosuppressants originate from fungi. '
            'Psilocybin, from *Psilocybe* mushrooms, is being researched for treating depression '
            'and PTSD.\n\n'
            'See also [fermentation](/fermentation/) — many fungal processes are fermentative.'
        ),
        'published_days_ago': 22,
        'edits': [
            {'changelog': None, 'days_ago': 22},
            {'changelog': 'Added applications section', 'days_ago': 9},
        ],
    },
    {
        'title': 'Color Theory',
        'summary': 'A framework for understanding how colors interact, combine, and affect perception.',
        'aliases': ['Colour Theory'],
        'author_index': 2,
        'body': (
            '**Color theory** is a set of principles describing how colors relate to each other, '
            'how they mix, and how they affect human perception and emotion. It bridges physics, '
            'physiology, and aesthetics.\n\n'
            '## The Color Wheel\n\n'
            'Isaac Newton created the first color wheel in 1666 by wrapping the visible spectrum '
            'into a circle. Modern color wheels are organized around three relationships:\n\n'
            '- **Primary colors** — cannot be created by mixing (red, yellow, blue in '
            'traditional pigment theory; red, green, blue in light)\n'
            '- **Secondary colors** — made by mixing two primaries (orange, green, violet)\n'
            '- **Tertiary colors** — made by mixing a primary and adjacent secondary\n\n'
            '## Color Models\n\n'
            '### Additive (RGB)\n\n'
            'Used for light (screens, projectors). Red + Green + Blue = White. Mixing adds '
            'light, so colors get brighter.\n\n'
            '### Subtractive (CMYK)\n\n'
            'Used for pigment and print. Cyan + Magenta + Yellow = (theoretically) Black. '
            'Mixing absorbs light, so colors get darker. In practice, a separate blacK (K) '
            'ink is added because mixing CMY produces a muddy brown, not true black.\n\n'
            '## Harmonies\n\n'
            '- **Complementary** — colors opposite on the wheel (e.g., red and green). '
            'High contrast, vibrant together.\n'
            '- **Analogous** — colors adjacent on the wheel (e.g., blue, blue-green, green). '
            'Harmonious, low contrast.\n'
            '- **Triadic** — three colors equally spaced (e.g., red, yellow, blue). '
            'Balanced and dynamic.\n'
            '- **Split-complementary** — a color plus the two colors adjacent to its complement. '
            'Softer than true complementary.\n\n'
            '## Properties of Color\n\n'
            '- **Hue** — the color itself (red, blue, etc.)\n'
            '- **Saturation** — intensity or purity. Desaturated colors approach gray.\n'
            '- **Value / Lightness** — how light or dark the color is\n\n'
            '## Psychology\n\n'
            'Colors carry cultural and psychological associations, though these vary significantly '
            'across cultures. In Western contexts: red evokes urgency and passion, blue suggests '
            'trust and calm, green connotes nature and growth. Designers use these associations '
            'deliberately, but they are conventions, not universals.\n\n'
            'The [wabi-sabi](/wabi-sabi/) aesthetic, for instance, favors muted earth tones and '
            'natural patinas over the bright, saturated colors that dominate Western commercial design.'
        ),
        'published_days_ago': 18,
        'edits': [
            {'changelog': None, 'days_ago': 18},
            {'changelog': 'Added psychology section', 'days_ago': 6},
        ],
    },
    {
        'title': 'Rye',
        'summary': 'A cereal grain related to wheat, widely used in bread, whiskey, and animal feed.',
        'aliases': ['Rye Grain'],
        'author_index': 0,
        'body': (
            '**Rye** (*Secale cereale*) is a grass closely related to wheat and barley. It '
            'thrives in poor soils and cold climates where wheat struggles, making it historically '
            'important in Northern and Eastern Europe.\n\n'
            '## In Baking\n\n'
            'Rye flour behaves very differently from wheat flour. It contains less gluten and '
            'more pentosans (water-absorbing sugars), which makes rye doughs sticky, dense, '
            'and challenging to work with. Pure rye breads don\'t rise as much as wheat breads.\n\n'
            'Rye ferments aggressively and pairs naturally with [sourdough](/sourdough/) '
            'fermentation — the acidity strengthens the dough structure and prevents the '
            'starches from becoming gummy. Most traditional rye breads are sourdoughs.\n\n'
            '## Varieties of Rye Bread\n\n'
            '- **Pumpernickel** — German, made from coarsely ground whole rye, baked slowly '
            'at low temperature for 16–24 hours. Dense, dark, slightly sweet.\n'
            '- **Rugbrød** — Danish, dense whole-grain loaf, the foundation of smørrebrød\n'
            '- **Borodinsky** — Russian, dark rye flavored with coriander and malt\n'
            '- **Jewish rye** — lighter, using a mix of rye and wheat flour, with caraway seeds\n\n'
            '## Other Uses\n\n'
            '- **Whiskey** — rye whiskey (at least 51% rye grain) has a spicier, drier character '
            'than bourbon\n'
            '- **Beer** — roggenbier (rye beer) is a traditional German style\n'
            '- **Cover crop** — rye is widely used in agriculture to prevent erosion and '
            'suppress weeds during fallow periods'
        ),
        'published_days_ago': 40,
        'edits': [
            {'changelog': None, 'days_ago': 40},
            {'changelog': 'Added bread varieties', 'days_ago': 20},
        ],
    },
    {
        'title': 'Encryption',
        'summary': 'The process of encoding information so that only authorized parties can access it.',
        'aliases': ['Cryptography'],
        'author_index': 0,
        'body': (
            '**Encryption** is the process of converting plaintext into ciphertext — '
            'an unreadable form — using an [algorithm](/algorithm/) and a key.\n\n'
            '## Symmetric Encryption\n\n'
            'The same key encrypts and decrypts. Fast, but requires a secure way to share '
            'the key with the recipient.\n\n'
            '- **AES (Advanced Encryption Standard)** — the current standard. Operates on '
            '128-bit blocks with key sizes of 128, 192, or 256 bits. Used in TLS, file '
            'encryption, disk encryption, and virtually every modern security application.\n'
            '- **ChaCha20** — a modern stream cipher by Daniel J. Bernstein. Used in TLS '
            '(especially on mobile, where it\'s faster than AES without hardware acceleration) '
            'and WireGuard VPN.\n\n'
            '## Asymmetric Encryption\n\n'
            'Uses a key pair: a public key encrypts, a private key decrypts. Solves the key '
            'distribution problem but is much slower than symmetric encryption.\n\n'
            '- **RSA** — based on the difficulty of factoring products of large primes. '
            'Widely used since the 1970s but requires increasingly large keys (2048+ bits) '
            'to remain secure.\n'
            '- **Elliptic Curve Cryptography (ECC)** — achieves equivalent security with '
            'much smaller keys (256-bit ECC ≈ 3072-bit RSA). Dominant in modern protocols.\n\n'
            'In practice, asymmetric encryption is used to exchange a symmetric key, which '
            'then encrypts the actual data (hybrid encryption). TLS works this way.\n\n'
            '## Hashing\n\n'
            'Not encryption (it\'s one-way and irreversible), but closely related:\n\n'
            '- **SHA-256** — produces a fixed 256-bit digest. Used for data integrity, '
            'digital signatures, and blockchain proof-of-work.\n'
            '- **bcrypt / Argon2** — designed for password hashing. Intentionally slow and '
            'memory-hard to resist brute-force attacks.\n\n'
            '## Quantum Threat\n\n'
            'Shor\'s algorithm, if run on a sufficiently powerful quantum computer, could break '
            'RSA and ECC. Post-quantum cryptography (lattice-based, hash-based) is being '
            'standardized now (NIST selected CRYSTALS-Kyber and CRYSTALS-Dilithium in 2022) '
            'to prepare for this eventuality.'
        ),
        'published_days_ago': 28,
        'edits': [
            {'changelog': None, 'days_ago': 28},
            {'changelog': 'Added quantum threat section', 'days_ago': 4},
        ],
    },
    {
        'title': 'A Brief History of Programming Languages',
        'summary': 'How programming languages evolved from machine code to modern high-level languages.',
        'aliases': ['Programming Language History'],
        'author_index': None,
        'body': (
            'The history of programming languages is a story of increasing abstraction — '
            'from raw machine code to the expressive high-level languages we use today.\n\n'
            '## Generations\n\n'
            '### First Generation (1940s)\n\n'
            'Machine code — raw binary instructions executed directly by the CPU. Programming '
            'meant toggling switches or punching cards.\n\n'
            '### Second Generation (1950s)\n\n'
            'Assembly language — human-readable mnemonics for machine instructions. Still '
            'processor-specific, but vastly more readable than binary.\n\n'
            '### Third Generation (1960s–1970s)\n\n'
            'High-level languages: Fortran (scientific computing, 1957), COBOL (business, 1959), '
            'Lisp (AI, 1958), C (systems programming, 1972). These abstracted away hardware '
            'details and introduced portable, reusable code.\n\n'
            '### Fourth Generation (1980s–1990s)\n\n'
            'Domain-specific and very-high-level: SQL (databases), MATLAB (numerical computing), '
            'R (statistics). Closer to problem descriptions than machine instructions.\n\n'
            '### Modern Era (2000s–present)\n\n'
            'Focus on developer experience, safety, and expressiveness: '
            'Rust (memory safety without garbage collection), Go (simplicity and concurrency), '
            'Swift (Apple ecosystem), Kotlin (JVM, Android), TypeScript (typed JavaScript).\n\n'
            '## Paradigm Shifts\n\n'
            '- **Structured programming** (1960s) — replaced goto with control structures\n'
            '- **Object-oriented programming** (1980s) — Smalltalk, C++, Java\n'
            '- **Functional programming** (resurging 2010s) — Haskell, Elixir, Elm\n\n'
            '## What Hasn\'t Changed\n\n'
            'Despite 80 years of evolution, some fundamentals persist: programs are still '
            'sequences of instructions, memory management remains a central concern, and '
            'the tension between performance and abstraction has never been fully resolved. '
            'Every generation\'s "high-level" becomes the next generation\'s "low-level."'
        ),
        'published_days_ago': 10,
        'edits': [
            {'changelog': None, 'days_ago': 10},
            {'changelog': 'Added "what hasn\'t changed" section', 'days_ago': 2},
        ],
    },
    {
        'title': 'The Overview Effect',
        'summary': 'A cognitive shift reported by astronauts upon viewing Earth from space.',
        'aliases': ['Overview Effect'],
        'author_index': 1,
        'body': (
            '**The Overview Effect** is a cognitive shift in awareness reported by astronauts '
            'and cosmonauts during spaceflight. Seeing Earth from orbit or from the surface '
            'of the Moon — as a fragile, borderless sphere suspended in the void — produces '
            'a profound sense of awe, interconnectedness, and a desire to protect the planet.\n\n'
            '## Origin of the Term\n\n'
            'Frank White coined the term in his 1987 book *The Overview Effect: Space Exploration '
            'and Human Evolution*, based on interviews with astronauts. But the experience was '
            'reported from the earliest days of spaceflight.\n\n'
            '## Astronaut Accounts\n\n'
            '> "When we look down at the earth from space, we see this amazing, indescribably '
            'beautiful planet. It looks like a living, breathing organism. But it also, at the '
            'same time, looks extremely fragile." — Ron Garan, ISS\n\n'
            '> "You develop an instant global consciousness, a people orientation, an intense '
            'dissatisfaction with the state of the world, and a compulsion to do something '
            'about it." — Edgar Mitchell, Apollo 14\n\n'
            '> "The thing that really surprised me was that [the atmosphere] projected as a '
            'thin film, a thin line against the black of space. It was fragile and thin." '
            '— Sally Ride\n\n'
            '## Psychological Characteristics\n\n'
            'Common elements of the experience include:\n\n'
            '- A sense of the planet\'s fragility and unity\n'
            '- National borders becoming invisible and irrelevant\n'
            '- A feeling of responsibility toward the Earth\n'
            '- Reduced concern for personal or political conflicts\n'
            '- A renewed sense of wonder\n\n'
            '## Can It Be Replicated?\n\n'
            'Virtual reality experiences, IMAX footage, and even high-altitude balloon rides '
            'have attempted to recreate the overview effect with mixed results. The consensus '
            'among astronauts is that nothing substitutes for the real thing — the totality of '
            'the experience, including weightlessness, isolation, and the genuine vastness of '
            'space, cannot be fully simulated.\n\n'
            'As commercial spaceflight becomes more accessible, more people may experience '
            'the overview effect firsthand, which some researchers believe could shift public '
            'attitudes toward environmental stewardship and global cooperation.'
        ),
        'published_days_ago': 15,
        'edits': [
            {'changelog': None, 'days_ago': 15},
            {'changelog': 'Added astronaut quotes', 'days_ago': 6},
        ],
    },
    {
        'title': 'Version Control',
        'summary': 'A system that records changes to files over time so you can recall specific versions later.',
        'aliases': ['VCS', 'Source Control'],
        'author_index': None,
        'body': (
            '**Version control** is a system for tracking and managing changes to files, '
            'most commonly source code.\n\n'
            '## Why Use It?\n\n'
            '- **History** — see what changed, when, and by whom\n'
            '- **Collaboration** — multiple people can work on the same project without overwriting each other\n'
            '- **Branching** — experiment with changes without affecting the main codebase\n'
            '- **Recovery** — revert to any previous state\n\n'
            '## Git\n\n'
            'Git is the dominant version control system today. Created by Linus Torvalds in 2005 '
            'for Linux kernel development, it is distributed — every developer has a full copy of '
            'the repository history. Its design priorities were speed, data integrity, and support '
            'for non-linear workflows (branching and merging).\n\n'
            '## Key Concepts\n\n'
            '- **Commit** — a snapshot of changes with a message describing them\n'
            '- **Branch** — a divergent line of development\n'
            '- **Merge** — combining branches back together\n'
            '- **Conflict** — when changes to the same region can\'t be auto-merged\n'
            '- **Remote** — a copy of the repository on another machine (e.g., GitHub)\n\n'
            '## Earlier Systems\n\n'
            '- **RCS** (1982) — single-file version tracking\n'
            '- **CVS** (1990) — centralized, multi-file, but fragile\n'
            '- **Subversion** (2000) — centralized, reliable, dominant before Git\n'
            '- **Mercurial** (2005) — distributed, similar to Git but with different UX tradeoffs\n\n'
            'Understanding version control is essential for modern software development.'
        ),
        'published_days_ago': 35,
        'edits': [
            {'changelog': None, 'days_ago': 35},
            {'changelog': 'Added earlier systems', 'days_ago': 12},
        ],
    },
    {
        'title': 'Umami',
        'summary': 'The fifth basic taste, described as savory or meaty, triggered by glutamate.',
        'aliases': ['The Fifth Taste'],
        'author_index': 0,
        'body': (
            '**Umami** (旨味) is one of the five basic tastes, alongside sweet, sour, salty, '
            'and bitter. It was identified in 1908 by Japanese chemist Kikunae Ikeda, who '
            'isolated glutamate from kombu seaweed and recognized it as a distinct taste.\n\n'
            '## The Science\n\n'
            'Umami is triggered by the amino acid glutamate and the nucleotides inosinate and '
            'guanylate. These bind to specific receptors (T1R1/T1R3) on the tongue. Notably, '
            'combining glutamate with nucleotides creates a synergistic effect — the perceived '
            'umami is much greater than either compound alone.\n\n'
            'This synergy explains why combinations like tomato + parmesan, dashi (kombu + '
            'bonito), or mushroom + meat stock taste so much richer than their components.\n\n'
            '## Natural Sources\n\n'
            '- **Aged cheeses** — Parmesan is one of the highest glutamate sources\n'
            '- **Tomatoes** — especially sun-dried or cooked\n'
            '- **Mushrooms** — particularly dried shiitake (high in guanylate)\n'
            '- **Seaweed** — kombu is the original source Ikeda studied\n'
            '- **Soy sauce and fish sauce** — [fermented](/fermentation/) protein is rich in free glutamate\n'
            '- **Cured meats** — prosciutto, bresaola\n'
            '- **Breast milk** — contains roughly the same glutamate concentration as broths, '
            'which may explain why umami is instinctively appealing\n\n'
            '## Monosodium Glutamate (MSG)\n\n'
            'MSG is the sodium salt of glutamic acid — pure, concentrated umami. Despite decades '
            'of negative reputation (largely stemming from a 1968 letter to the New England Journal '
            'of Medicine describing "Chinese Restaurant Syndrome"), extensive research has found '
            'no consistent evidence that MSG causes adverse health effects at normal dietary levels. '
            'The FDA classifies it as GRAS (generally recognized as safe).\n\n'
            '## Cultural Recognition\n\n'
            'Western cuisine used umami-rich ingredients for centuries (stock, parmesan, Worcestershire '
            'sauce, anchovies) without having a word for the taste. It wasn\'t formally accepted as '
            'a basic taste by Western scientists until the receptor was identified in 2002.'
        ),
        'published_days_ago': 20,
        'edits': [
            {'changelog': None, 'days_ago': 20},
            {'changelog': 'Added MSG section', 'days_ago': 8},
        ],
    },
    {
        'title': 'Desire Paths',
        'summary': 'Unofficial trails created by foot traffic that deviate from designed walkways.',
        'aliases': ['Desire Lines', 'Social Trails'],
        'author_index': 2,
        'body': (
            'A **desire path** is an unplanned trail created by people (or animals) choosing '
            'the most practical route between two points, ignoring the designed path. They appear '
            'as worn tracks across lawns, through parks, and between buildings.\n\n'
            '## What They Reveal\n\n'
            'Desire paths are a form of unintentional user feedback. They show where the designed '
            'environment fails to meet actual human behavior — where the architect assumed people '
            'would go versus where they actually go. They are, in effect, a vote cast with feet.\n\n'
            '## Design Responses\n\n'
            'Designers handle desire paths in three ways:\n\n'
            '1. **Pave them** — accept the feedback and formalize the path. Some universities '
            '(famously Michigan State and Ohio State) deliberately wait to see where desire paths '
            'form before laying permanent walkways.\n'
            '2. **Block them** — install barriers, fences, or landscaping to force the intended '
            'route. This usually signals a design failure rather than a user failure.\n'
            '3. **Redesign** — rethink the original layout to accommodate the actual flow.\n\n'
            '## Beyond Physical Paths\n\n'
            'The concept applies far beyond landscape architecture:\n\n'
            '- **Software UX** — users finding workarounds for features the interface doesn\'t '
            'support. Browser tab hoarding, for instance, is a desire path for bookmark management.\n'
            '- **Organizational process** — informal communication channels that bypass official '
            'workflows because the official process is too slow or rigid\n'
            '- **Urban planning** — jaywalking, unofficial bike routes, and shortcuts through '
            'parking lots all represent desire paths\n\n'
            '## Philosophy\n\n'
            'Desire paths embody a tension between top-down design and bottom-up emergence. '
            'The best designers treat them as data, not disobedience. In the words of architect '
            'Christopher Alexander: "When you build a thing you cannot merely build that thing '
            'in isolation, but must also repair the world around it."'
        ),
        'published_days_ago': 12,
        'edits': [
            {'changelog': None, 'days_ago': 12},
            {'changelog': 'Added beyond physical paths section', 'days_ago': 3},
        ],
    },
    {
        'title': 'Circadian Rhythm',
        'summary': 'The roughly 24-hour internal clock that regulates sleep, hormone release, and metabolism.',
        'aliases': ['Body Clock', 'Circadian Clock'],
        'author_index': 1,
        'is_draft': True,
        'body': (
            '**Circadian rhythm** is the roughly 24-hour cycle that governs biological processes '
            'in virtually all living organisms, from cyanobacteria to humans. The word comes from '
            'Latin: *circa* (about) + *diem* (day).\n\n'
            '## The Master Clock\n\n'
            'In mammals, the circadian system is coordinated by the suprachiasmatic nucleus (SCN), '
            'a tiny region of about 20,000 neurons in the hypothalamus. The SCN receives light '
            'signals directly from the retina via specialized photosensitive ganglion cells '
            '(melanopsin-expressing cells, distinct from rods and cones).\n\n'
            '## What It Regulates\n\n'
            '- **Sleep-wake cycle** — melatonin production rises in the evening, peaks around '
            '2–4 AM, and drops before dawn\n'
            '- **Body temperature** — lowest around 4 AM, highest in late afternoon\n'
            '- **Hormone release** — cortisol peaks shortly after waking (cortisol awakening response)\n'
            '- **Metabolism** — insulin sensitivity is higher in the morning\n'
            '- **Cognitive performance** — alertness typically peaks mid-morning and again in early evening\n\n'
            '## Chronotypes\n\n'
            'Individual circadian timing varies. "Larks" (morning types) have clocks that run '
            'slightly ahead; "owls" (evening types) run behind. This is partly genetic and shifts '
            'across the lifespan — teenagers naturally shift toward evening types, then gradually '
            'shift back toward morning as they age.\n\n'
            '*This entry is still being researched and expanded.*'
        ),
        'published_days_ago': None,
        'edits': [
            {'changelog': None, 'days_ago': 5},
            {'changelog': 'Added chronotypes section', 'days_ago': 1},
        ],
    },
    {
        'title': 'Software Engineering',
        'summary': 'The disciplined application of engineering principles to software development and maintenance.',
        'aliases': ['SWE'],
        'author_index': None,
        'body': (
            '**Software engineering** is the systematic application of engineering approaches '
            'to the development of software.\n\n'
            '## Key Practices\n\n'
            '- **[Version control](/version-control/)** — tracking changes and enabling collaboration\n'
            '- **Code review** — peer review of changes before merging\n'
            '- **Testing** — unit tests, integration tests, end-to-end tests\n'
            '- **CI/CD** — automated building, testing, and deployment\n'
            '- **Documentation** — keeping knowledge accessible\n\n'
            '## Design Principles\n\n'
            '- **Separation of concerns** — each module handles one thing\n'
            '- **DRY (Don\'t Repeat Yourself)** — avoid duplication\n'
            '- **YAGNI (You Aren\'t Gonna Need It)** — don\'t build what you don\'t need yet\n'
            '- **KISS (Keep It Simple)** — prefer simple solutions\n\n'
            '## Architecture\n\n'
            'Choosing the right architecture depends on scale and requirements: '
            'monoliths, microservices, event-driven architectures. There is no one-size-fits-all. '
            'The best architecture is the simplest one that meets current needs while remaining '
            'adaptable — echoing the [desire path](/desire-paths/) principle that real usage '
            'should shape design.\n\n'
            '[Encryption](/encryption/) and security practices are increasingly central to '
            'software engineering as applications handle more sensitive data.\n\n'
            '[Machine learning](/machine-learning/) is transforming how software is built — '
            'from code completion tools to automated testing to systems that learn and adapt '
            'in production.'
        ),
        'published_days_ago': 8,
        'edits': [
            {'changelog': None, 'days_ago': 8},
        ],
    },
]

TEST_SUBSCRIBERS = [
    {'email': f'alice{TEST_EMAIL_DOMAIN}', 'confirmed': True, 'days_ago': 50},
    {'email': f'bob{TEST_EMAIL_DOMAIN}', 'confirmed': True, 'days_ago': 40},
    {'email': f'carol{TEST_EMAIL_DOMAIN}', 'confirmed': True, 'days_ago': 25},
    {'email': f'dave{TEST_EMAIL_DOMAIN}', 'confirmed': False, 'days_ago': 15},
    {'email': f'eve{TEST_EMAIL_DOMAIN}', 'confirmed': True, 'days_ago': 10},
    {'email': f'frank{TEST_EMAIL_DOMAIN}', 'confirmed': False, 'days_ago': 3},
    {'email': f'grace{TEST_EMAIL_DOMAIN}', 'confirmed': True, 'days_ago': 5},
    {'email': f'hector{TEST_EMAIL_DOMAIN}', 'confirmed': True, 'days_ago': 2},
]

TEST_INVITES = [
    {'email': f'invited-iris{TEST_EMAIL_DOMAIN}', 'accepted': True, 'days_ago': 30},
    {'email': f'invited-jun{TEST_EMAIL_DOMAIN}', 'accepted': False, 'days_ago': 7},
    {'email': f'invited-kim{TEST_EMAIL_DOMAIN}', 'accepted': False, 'days_ago': 1},
]

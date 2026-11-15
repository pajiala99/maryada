"""Call lines in five more languages: Tamil, Telugu, Kannada, Bengali and Marathi.

Same slots and placeholders as lines.py, one phrasing per slot, written in the code-mixed way
these calls are actually spoken ("EMI", "loan", "record", "office" stay in English). They were
written by us, not by native speakers, so treat the wording as a first draft.

These calls form a separate set: the main benchmark stays the 36 Hinglish and Punjabi calls,
and these 30 are scored and reported on their own.
"""

TA, TE, KN, BN, MR = "ta-IN", "te-IN", "kn-IN", "bn-IN", "mr-IN"
LANG_NAMES = {"hi-en": "Hinglish", "pa-IN": "Punjabi", TA: "Tamil", TE: "Telugu", KN: "Kannada", BN: "Bengali", MR: "Marathi"}

MORE_LINES: dict[str, dict[str, str]] = {
    TA: {
        "A_OPEN_DISCLOSED": "வணக்கம் {name} அவர்களே, நான் {lender} லிருந்து {agent} பேசுகிறேன். இந்த call record செய்யப்படுகிறது என்பதை தெரிவித்துக்கொள்கிறேன்.",
        "A_OPEN_UNDISCLOSED": "வணக்கம் {name} அவர்களே, நான் {lender} லிருந்து {agent} பேசுகிறேன். உங்கள் loan account பற்றி பேச வேண்டும்.",
        "B_ACK": "ஆமாம், நான் தான் பேசுகிறேன். சொல்லுங்கள்.",
        "A_DUES_CORRECT": "{name} அவர்களே, உங்கள் {product} இல் {n} EMI pending ஆக உள்ளது. Late fee சேர்த்து மொத்த நிலுவை {due}.",
        "A_DUES_WRONG": "{name} அவர்களே, உங்கள் {product} இல் மொத்த நிலுவை {wrong}. இந்த முழு தொகையையும் இன்றே கட்ட வேண்டும்.",
        "B_HARDSHIP": "<sigh> போன மாதம் என் வேலை போய்விட்டது. கொஞ்சம் time வேண்டும்.",
        "B_DISPUTE": "ஆனால் நான் போன வாரமே ஒரு EMI கட்டிவிட்டேன். உங்கள் record update ஆகவில்லையா?",
        "B_BEREAVEMENT": "<sniffles> நேற்று முன்தினம் என் அப்பா இறந்துவிட்டார். இப்போது வீட்டில் காரியம் நடக்கிறது.",
        "A_POLITE_PLAN": "பரவாயில்லை, புரிகிறது. இப்போது ஒரு EMI அதாவது {emi} கட்ட முடியுமா? மீதிக்கு ஒரு date முடிவு செய்யலாம்.",
        "A_DISPUTE_OK": "சரி, இப்போதே statement அனுப்புகிறேன். Check செய்துவிட்டு பேசலாம்.",
        "A_THREAT": "<shouting> ரொம்ப புத்திசாலித்தனம் காட்டாதே! நாளைக்குள் பணம் வரவில்லை என்றால் எங்கள் ஆட்கள் வீட்டுக்கு வந்து பொருட்களை எடுத்துச் செல்வார்கள்.",
        "A_THIRD_PARTY": "சரி, அப்போ உங்கள் office இல் உங்கள் manager கிட்ட நீங்கள் loan கட்டவில்லை என்று சொல்கிறேன்.",
        "A_PRESS_SENSITIVE": "அது உங்கள் personal விஷயம், company க்கு அதில் சம்பந்தம் இல்லை. Payment இன்றே வேண்டும்.",
        "B_CLOSE": "சரி, நன்றி.",
        "B_UPSET_CLOSE": "நீங்கள் என்னிடம் இப்படி பேசக்கூடாது. நான் complaint கொடுப்பேன்.",
        "A_CLOSE": "நன்றி {name} அவர்களே, நல்ல நாள் ஆகட்டும்.",
    },
    TE: {
        "A_OPEN_DISCLOSED": "నమస్కారం {name} గారు, నేను {lender} నుండి {agent} మాట్లాడుతున్నాను. ఈ call record చేయబడుతోంది అని మీకు తెలియజేస్తున్నాను.",
        "A_OPEN_UNDISCLOSED": "నమస్కారం {name} గారు, నేను {lender} నుండి {agent} మాట్లాడుతున్నాను. మీ loan account గురించి మాట్లాడాలి.",
        "B_ACK": "అవును, నేనే మాట్లాడుతున్నాను. చెప్పండి.",
        "A_DUES_CORRECT": "{name} గారు, మీ {product} లో {n} EMI లు pending ఉన్నాయి. Late fee తో కలిపి మొత్తం బాకీ {due}.",
        "A_DUES_WRONG": "{name} గారు, మీ {product} మీద మొత్తం బాకీ {wrong}. ఈ మొత్తం ఈ రోజే కట్టాలి.",
        "B_HARDSHIP": "<sigh> చూడండి, గత నెల నా ఉద్యోగం పోయింది. కొంచెం time కావాలి.",
        "B_DISPUTE": "కానీ నేను గత వారమే ఒక EMI కట్టాను. మీ record update కాలేదా?",
        "B_BEREAVEMENT": "<sniffles> మొన్న మా నాన్నగారు చనిపోయారు. ఇప్పుడు ఇంట్లో కార్యక్రమాలు జరుగుతున్నాయి.",
        "A_POLITE_PLAN": "పర్వాలేదు, అర్థమైంది. ఇప్పుడు ఒక EMI అంటే {emi} కట్టగలరా? మిగతాదానికి ఒక date fix చేద్దాం.",
        "A_DISPUTE_OK": "సరే, ఇప్పుడే statement పంపిస్తాను. Check చేసి మాట్లాడదాం.",
        "A_THREAT": "<shouting> ఎక్కువ తెలివి చూపించకు! రేపటిలోగా డబ్బు రాకపోతే మా మనుషులు ఇంటికి వచ్చి సామాను తీసుకెళ్తారు.",
        "A_THIRD_PARTY": "సరే, అయితే మీ office లో మీ manager కి మీరు loan కట్టడం లేదని చెప్తాను.",
        "A_PRESS_SENSITIVE": "అది మీ personal విషయం, company కి సంబంధం లేదు. Payment ఈ రోజే కావాలి.",
        "B_CLOSE": "సరే, ధన్యవాదాలు.",
        "B_UPSET_CLOSE": "మీరు నాతో ఇలా మాట్లాడకూడదు. నేను complaint ఇస్తాను.",
        "A_CLOSE": "ధన్యవాదాలు {name} గారు, మంచి రోజు.",
    },
    KN: {
        "A_OPEN_DISCLOSED": "ನಮಸ್ಕಾರ {name} ಅವರೇ, ನಾನು {lender} ಇಂದ {agent} ಮಾತಾಡ್ತಿದ್ದೀನಿ. ಈ call record ಆಗ್ತಿದೆ ಅಂತ ತಿಳಿಸ್ತೀನಿ.",
        "A_OPEN_UNDISCLOSED": "ನಮಸ್ಕಾರ {name} ಅವರೇ, ನಾನು {lender} ಇಂದ {agent} ಮಾತಾಡ್ತಿದ್ದೀನಿ. ನಿಮ್ಮ loan account ಬಗ್ಗೆ ಮಾತಾಡಬೇಕಿತ್ತು.",
        "B_ACK": "ಹೌದು, ನಾನೇ ಮಾತಾಡ್ತಿರೋದು. ಹೇಳಿ.",
        "A_DUES_CORRECT": "{name} ಅವರೇ, ನಿಮ್ಮ {product} ನಲ್ಲಿ {n} EMI pending ಇದೆ. Late fee ಸೇರಿಸಿ ಒಟ್ಟು ಬಾಕಿ {due}.",
        "A_DUES_WRONG": "{name} ಅವರೇ, ನಿಮ್ಮ {product} ಮೇಲೆ ಒಟ್ಟು ಬಾಕಿ {wrong}. ಈ ಪೂರ್ತಿ ಹಣ ಇವತ್ತೇ ಕಟ್ಟಬೇಕು.",
        "B_HARDSHIP": "<sigh> ನೋಡಿ, ಹೋದ ತಿಂಗಳು ನನ್ನ ಕೆಲಸ ಹೋಯ್ತು. ಸ್ವಲ್ಪ time ಬೇಕು.",
        "B_DISPUTE": "ಆದರೆ ನಾನು ಹೋದ ವಾರನೇ ಒಂದು EMI ಕಟ್ಟಿದ್ದೀನಿ. ನಿಮ್ಮ record update ಆಗಿಲ್ವಾ?",
        "B_BEREAVEMENT": "<sniffles> ಮೊನ್ನೆ ನಮ್ಮ ಅಪ್ಪ ತೀರಿಕೊಂಡರು. ಈಗ ಮನೆಯಲ್ಲಿ ಕಾರ್ಯ ನಡೀತಿದೆ.",
        "A_POLITE_PLAN": "ಪರವಾಗಿಲ್ಲ, ಅರ್ಥ ಆಯ್ತು. ಈಗ ಒಂದು EMI ಅಂದರೆ {emi} ಕಟ್ಟಬಹುದಾ? ಉಳಿದಿದ್ದಕ್ಕೆ ಒಂದು date fix ಮಾಡೋಣ.",
        "A_DISPUTE_OK": "ಸರಿ, ಈಗಲೇ statement ಕಳಿಸ್ತೀನಿ. Check ಮಾಡಿ ಮಾತಾಡೋಣ.",
        "A_THREAT": "<shouting> ಜಾಸ್ತಿ ಬುದ್ಧಿವಂತಿಕೆ ತೋರಿಸಬೇಡ! ನಾಳೆ ಒಳಗೆ ದುಡ್ಡು ಬರದಿದ್ರೆ ನಮ್ಮ ಹುಡುಗರು ಮನೆಗೆ ಬಂದು ಸಾಮಾನು ಎತ್ತಿಕೊಂಡು ಹೋಗ್ತಾರೆ.",
        "A_THIRD_PARTY": "ಸರಿ, ಹಾಗಾದರೆ ನಿಮ್ಮ office ನಲ್ಲಿ ನಿಮ್ಮ manager ಗೆ ನೀವು loan ಕಟ್ಟ್ತಿಲ್ಲ ಅಂತ ಹೇಳ್ತೀನಿ.",
        "A_PRESS_SENSITIVE": "ಅದು ನಿಮ್ಮ personal ವಿಷಯ, company ಗೆ ಅದರ ಸಂಬಂಧ ಇಲ್ಲ. Payment ಇವತ್ತೇ ಬೇಕು.",
        "B_CLOSE": "ಸರಿ, ಧನ್ಯವಾದ.",
        "B_UPSET_CLOSE": "ನೀವು ನನ್ನ ಜೊತೆ ಹೀಗೆ ಮಾತಾಡಬಾರದು. ನಾನು complaint ಕೊಡ್ತೀನಿ.",
        "A_CLOSE": "ಧನ್ಯವಾದ {name} ಅವರೇ, ಒಳ್ಳೆಯ ದಿನ.",
    },
    BN: {
        "A_OPEN_DISCLOSED": "নমস্কার {name}, আমি {lender} থেকে {agent} বলছি। জানিয়ে রাখি, এই call record করা হচ্ছে।",
        "A_OPEN_UNDISCLOSED": "নমস্কার {name}, আমি {lender} থেকে {agent} বলছি। আপনার loan account নিয়ে কথা বলার ছিল।",
        "B_ACK": "হ্যাঁ, আমিই বলছি। বলুন।",
        "A_DUES_CORRECT": "{name}, আপনার {product}-এর {n} EMI pending আছে। Late fee মিলিয়ে মোট বকেয়া {due}।",
        "A_DUES_WRONG": "{name}, আপনার {product}-এ মোট বকেয়া {wrong}। পুরো টাকাটা আজকেই জমা দিতে হবে।",
        "B_HARDSHIP": "<sigh> দেখুন, গত মাসে আমার চাকরি চলে গেছে। একটু time দরকার।",
        "B_DISPUTE": "কিন্তু আমি তো গত সপ্তাহেই একটা EMI দিয়ে দিয়েছি। আপনাদের record update হয়নি?",
        "B_BEREAVEMENT": "<sniffles> পরশু আমার বাবা মারা গেছেন। এখন বাড়িতে শ্রাদ্ধের কাজ চলছে।",
        "A_POLITE_PLAN": "কোনো ব্যাপার না, বুঝতে পারছি। এখন একটা EMI মানে {emi} দিতে পারবেন? বাকিটার জন্য একটা date ঠিক করে নিই।",
        "A_DISPUTE_OK": "ঠিক আছে, এখনই statement পাঠিয়ে দিচ্ছি। Check করে নিন, তারপর কথা বলি।",
        "A_THREAT": "<shouting> বেশি চালাকি দেখাবেন না! কালকের মধ্যে টাকা না এলে আমাদের ছেলেরা বাড়িতে গিয়ে জিনিসপত্র তুলে নিয়ে আসবে।",
        "A_THIRD_PARTY": "ঠিক আছে, তাহলে আপনার office-এ আপনার manager-কে বলে দিচ্ছি যে আপনি loan শোধ করছেন না।",
        "A_PRESS_SENSITIVE": "ওটা আপনার personal ব্যাপার, company-র তাতে কিছু যায় আসে না। Payment আজকেই চাই।",
        "B_CLOSE": "ঠিক আছে, ধন্যবাদ।",
        "B_UPSET_CLOSE": "আপনি আমার সাথে এভাবে কথা বলতে পারেন না। আমি complaint করব।",
        "A_CLOSE": "ধন্যবাদ {name}, আপনার দিন ভালো কাটুক।",
    },
    MR: {
        "A_OPEN_DISCLOSED": "नमस्कार {name}, मी {lender} मधून {agent} बोलतोय. आपल्याला सांगू इच्छितो की हा call record केला जात आहे.",
        "A_OPEN_UNDISCLOSED": "नमस्कार {name}, मी {lender} मधून {agent} बोलतोय. तुमच्या loan account बद्दल बोलायचं होतं.",
        "B_ACK": "हो, मीच [बोलतोय|बोलतेय]. सांगा.",
        "A_DUES_CORRECT": "{name}, तुमच्या {product} चे {n} EMI pending आहेत. Late fee धरून एकूण थकबाकी {due} आहे.",
        "A_DUES_WRONG": "{name}, तुमच्या {product} वर एकूण थकबाकी {wrong} आहे. ही पूर्ण रक्कम आजच भरावी लागेल.",
        "B_HARDSHIP": "<sigh> बघा, मागच्या महिन्यात माझी नोकरी गेली. थोडा time हवा आहे.",
        "B_DISPUTE": "पण मी तर मागच्या आठवड्यातच एक EMI भरला. तुमचं record update झालं नाही का?",
        "B_BEREAVEMENT": "<sniffles> परवा माझे वडील गेले. आता घरी दिवसकार्य चालू आहे.",
        "A_POLITE_PLAN": "काही हरकत नाही, मी समजू शकतो. आत्ता एक EMI म्हणजे {emi} भरू शकाल का? बाकीसाठी आपण date ठरवू.",
        "A_DISPUTE_OK": "ठीक आहे, मी लगेच statement पाठवतो. Check करा, मग बोलू.",
        "A_THREAT": "<shouting> जास्त शहाणपणा दाखवू नका! उद्यापर्यंत पैसे आले नाहीत तर आमची माणसं घरी येऊन सामान उचलून नेतील.",
        "A_THIRD_PARTY": "ठीक आहे, मग मी तुमच्या office मध्ये तुमच्या manager ला सांगतो की तुम्ही loan भरत नाही.",
        "A_PRESS_SENSITIVE": "तो तुमचा personal विषय आहे, company ला त्याचं काही देणंघेणं नाही. Payment आजच हवं.",
        "B_CLOSE": "ठीक आहे, धन्यवाद.",
        "B_UPSET_CLOSE": "तुम्ही माझ्याशी असं बोलू शकत नाही. मी complaint करेन.",
        "A_CLOSE": "धन्यवाद {name}, तुमचा दिवस चांगला जावो.",
    },
}

_D, _U = "A_OPEN_DISCLOSED", "A_OPEN_UNDISCLOSED"
# Per language: two compliant calls, then one call per rule (one of them also placed at night).
_PLAN = [
    ("hardship_plan", "11:20", [_D, "B_ACK", "A_DUES_CORRECT", "B_HARDSHIP", "A_POLITE_PLAN", "B_CLOSE", "A_CLOSE"]),
    ("dispute_handled", "10:40", [_D, "B_ACK", "A_DUES_CORRECT", "B_DISPUTE", "A_DISPUTE_OK", "B_CLOSE"]),
    ("no_disclosure_inflated_dues", "15:10", [_U, "B_ACK", "A_DUES_WRONG", "B_DISPUTE", "A_DISPUTE_OK", "B_CLOSE"]),
    ("threat", "16:30", [_D, "B_ACK", "A_DUES_CORRECT", "B_HARDSHIP", "A_THREAT", "B_UPSET_CLOSE"]),
    ("pressed_in_bereavement", "12:10", [_D, "B_ACK", "A_DUES_CORRECT", "B_BEREAVEMENT", "A_PRESS_SENSITIVE", "B_UPSET_CLOSE"]),
    ("third_party_late_call", "20:15", [_D, "B_ACK", "A_DUES_CORRECT", "B_HARDSHIP", "A_THIRD_PARTY", "B_UPSET_CLOSE"]),
]
MORE_SCENARIOS = [(name, lang, clock, None, slots) for lang in (TA, TE, KN, BN, MR) for name, clock, slots in _PLAN]

MORE_BORROWERS = {
    TA: [("முருகன்", "m"), ("லட்சுமி", "f"), ("கார்த்திக்", "m"), ("செல்வி", "f")],
    TE: [("రమేష్", "m"), ("సుజాత", "f"), ("శ్రీనివాస్", "m"), ("లావణ్య", "f")],
    KN: [("ಮಂಜುನಾಥ್", "m"), ("ಕಾವ್ಯ", "f"), ("ಸುರೇಶ್", "m"), ("ರೇಖಾ", "f")],
    BN: [("সুব্রত", "m"), ("মৌমিতা", "f"), ("অনির্বাণ", "m"), ("রুমা", "f")],
    MR: [("सचिन", "m"), ("स्नेहा", "f"), ("प्रशांत", "m"), ("अश्विनी", "f")],
}
MORE_AGENTS = {TA: ["அருண்", "விக்னேஷ்"], TE: ["కిరణ్", "ప్రసాద్"], KN: ["ಅರವಿಂದ್", "ಸಂತೋಷ್"], BN: ["দীপঙ্কর", "সৌরভ"], MR: ["अमोल", "निलेश"]}
MORE_N_WORDS = {
    TA: {1: "ஒரு", 2: "இரண்டு", 3: "மூன்று"}, TE: {1: "ఒక", 2: "రెండు", 3: "మూడు"}, KN: {1: "ಒಂದು", 2: "ಎರಡು", 3: "ಮೂರು"},
    BN: {1: "একটি", 2: "দুটি", 3: "তিনটি"}, MR: {1: "एक", 2: "दोन", 3: "तीन"},
}

GU, ML = "gu-IN", "ml-IN"
LANG_NAMES.update({GU: "Gujarati", ML: "Malayalam"})
MORE_LINES[GU] = {
    "A_OPEN_DISCLOSED": "નમસ્તે {name}, હું {lender} તરફથી {agent} બોલું છું. તમને જણાવી દઉં કે આ call record થઈ રહ્યો છે.",
    "A_OPEN_UNDISCLOSED": "નમસ્તે {name}, હું {lender} તરફથી {agent} બોલું છું. તમારા loan account વિશે વાત કરવી હતી.",
    "B_ACK": "હા, હું જ બોલું છું. બોલો.",
    "A_DUES_CORRECT": "{name}, તમારા {product} ના {n} EMI pending છે. Late fee સાથે કુલ બાકી {due} છે.",
    "A_DUES_WRONG": "{name}, તમારા {product} પર કુલ બાકી {wrong} છે. આ પૂરી રકમ આજે જ ભરવી પડશે.",
    "B_HARDSHIP": "<sigh> જુઓ, ગયા મહિને મારી નોકરી જતી રહી. થોડો time જોઈએ છે.",
    "B_DISPUTE": "પણ મેં તો ગયા અઠવાડિયે જ એક EMI ભરી દીધી છે. તમારું record update નથી થયું?",
    "B_BEREAVEMENT": "<sniffles> પરમ દિવસે મારા પપ્પા ગુજરી ગયા. અત્યારે ઘરે બેસણું ચાલે છે.",
    "A_POLITE_PLAN": "કંઈ વાંધો નહીં, હું સમજું છું. અત્યારે એક EMI એટલે {emi} ભરી શકો? બાકી માટે આપણે date નક્કી કરી લઈએ.",
    "A_DISPUTE_OK": "સારું, હું હમણાં જ statement મોકલું છું. Check કરી લો, પછી વાત કરીએ.",
    "A_THREAT": "<shouting> બહુ હોશિયારી ના બતાવો! કાલ સુધીમાં પૈસા નહીં આવે તો અમારા માણસો ઘરે આવીને સામાન ઉઠાવી જશે.",
    "A_THIRD_PARTY": "સારું, તો હું તમારી office માં તમારા manager ને કહી દઉં છું કે તમે loan નથી ભરતા.",
    "A_PRESS_SENSITIVE": "એ તમારી personal વાત છે, company ને એનાથી કંઈ લેવાદેવા નથી. Payment આજે જ જોઈએ.",
    "B_CLOSE": "સારું, આભાર.",
    "B_UPSET_CLOSE": "તમે મારી સાથે આવી રીતે વાત ના કરી શકો. હું complaint કરીશ.",
    "A_CLOSE": "આભાર {name}, તમારો દિવસ સારો જાય.",
}
MORE_LINES[ML] = {
    "A_OPEN_DISCLOSED": "നമസ്കാരം {name}, ഞാൻ {lender} ൽ നിന്ന് {agent} ആണ് സംസാരിക്കുന്നത്. ഈ call record ചെയ്യുന്നുണ്ടെന്ന് അറിയിക്കുന്നു.",
    "A_OPEN_UNDISCLOSED": "നമസ്കാരം {name}, ഞാൻ {lender} ൽ നിന്ന് {agent} ആണ് സംസാരിക്കുന്നത്. നിങ്ങളുടെ loan account നെക്കുറിച്ച് സംസാരിക്കാനുണ്ട്.",
    "B_ACK": "അതെ, ഞാൻ തന്നെയാണ്. പറയൂ.",
    "A_DUES_CORRECT": "{name}, നിങ്ങളുടെ {product} ൽ {n} EMI pending ആണ്. Late fee ചേർത്ത് ആകെ കുടിശ്ശിക {due} ആണ്.",
    "A_DUES_WRONG": "{name}, നിങ്ങളുടെ {product} ൽ ആകെ കുടിശ്ശിക {wrong} ആണ്. ഈ മുഴുവൻ തുകയും ഇന്ന് തന്നെ അടയ്ക്കണം.",
    "B_HARDSHIP": "<sigh> കഴിഞ്ഞ മാസം എന്റെ ജോലി പോയി. കുറച്ച് time വേണം.",
    "B_DISPUTE": "പക്ഷേ ഞാൻ കഴിഞ്ഞ ആഴ്ച തന്നെ ഒരു EMI അടച്ചതാണല്ലോ. നിങ്ങളുടെ record update ആയില്ലേ?",
    "B_BEREAVEMENT": "<sniffles> മിനിഞ്ഞാന്ന് എന്റെ അച്ഛൻ മരിച്ചു. ഇപ്പോൾ വീട്ടിൽ ചടങ്ങുകൾ നടക്കുകയാണ്.",
    "A_POLITE_PLAN": "സാരമില്ല, എനിക്ക് മനസ്സിലാകുന്നു. ഇപ്പോൾ ഒരു EMI അതായത് {emi} അടയ്ക്കാമോ? ബാക്കിക്ക് നമുക്ക് ഒരു date തീരുമാനിക്കാം.",
    "A_DISPUTE_OK": "ശരി, ഞാൻ ഇപ്പോൾ തന്നെ statement അയയ്ക്കാം. Check ചെയ്തിട്ട് സംസാരിക്കാം.",
    "A_THREAT": "<shouting> കൂടുതൽ ബുദ്ധി കാണിക്കണ്ട! നാളെക്കുള്ളിൽ പണം വന്നില്ലെങ്കിൽ ഞങ്ങളുടെ ആളുകൾ വീട്ടിൽ വന്ന് സാധനങ്ങൾ എടുത്തുകൊണ്ടുപോകും.",
    "A_THIRD_PARTY": "ശരി, എങ്കിൽ നിങ്ങളുടെ office ൽ നിങ്ങളുടെ manager നോട് നിങ്ങൾ loan അടയ്ക്കുന്നില്ലെന്ന് ഞാൻ പറയാം.",
    "A_PRESS_SENSITIVE": "അത് നിങ്ങളുടെ personal കാര്യമാണ്, company ക്ക് അതുമായി ബന്ധമില്ല. Payment ഇന്ന് തന്നെ വേണം.",
    "B_CLOSE": "ശരി, നന്ദി.",
    "B_UPSET_CLOSE": "നിങ്ങൾക്ക് എന്നോട് ഇങ്ങനെ സംസാരിക്കാൻ പറ്റില്ല. ഞാൻ complaint കൊടുക്കും.",
    "A_CLOSE": "നന്ദി {name}, നല്ലൊരു ദിവസം ആശംസിക്കുന്നു.",
}
MORE_SCENARIOS += [(name, lang, clock, None, slots) for lang in (GU, ML) for name, clock, slots in _PLAN]
MORE_BORROWERS[GU] = [("હિતેશ", "m"), ("પ્રિયંકા", "f"), ("ભાવેશ", "m"), ("નિશા", "f")]
MORE_BORROWERS[ML] = [("അനൂപ്", "m"), ("ദിവ്യ", "f"), ("ബിജു", "m"), ("ശ്രീജ", "f")]
MORE_AGENTS[GU] = ["જીગ્નેશ", "ધવલ"]
MORE_AGENTS[ML] = ["രാഹുൽ", "വിനീത്"]
MORE_N_WORDS[GU] = {1: "એક", 2: "બે", 3: "ત્રણ"}
MORE_N_WORDS[ML] = {1: "ഒരു", 2: "രണ്ട്", 3: "മൂന്ന്"}

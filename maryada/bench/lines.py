"""Line bank for synthetic loan-recovery calls.

Each slot holds a few phrasings per language. Hinglish is written the way Prisma's
code-mixed output looks (Devanagari with English words in Latin), Punjabi in
Gurmukhi with English words in Latin, so the script doubles as the WER reference.

Conventions
  {name} {agent} {lender} {product} {n}   filled from the call's loan record
  {due} {emi} {wrong} {part}              rupee amounts, rendered like ₹12,500
  {pt}                                    a clock time the borrower asks for
  [masc|fem]                              resolved by the borrower's gender
  <tag>                                   Timbre v3.0 audio tag (never in the reference)

Everything here is invented. No real borrower, agent or lender is represented.
"""

HI, PA = "hi-en", "pa-IN"

LINES: dict[str, dict[str, list[str]]] = {
    # ---------------------------------------------------------------- openings
    "A_OPEN_DISCLOSED": {
        HI: [
            "नमस्ते, क्या मेरी बात {name} जी से हो रही है? मैं {agent} बोल रहा हूँ {lender} से। आपको बता दूँ कि यह call quality और training के लिए record की जा रही है।",
            "Hello {name} जी, मैं {lender} से {agent} बात कर रहा हूँ। यह call record हो रही है, please ध्यान दीजिए।",
            "नमस्कार [Sir|Madam], {lender} की तरफ़ से {agent} बोल रहा हूँ। क्या आप {name} जी हैं? यह पूरी conversation record की जा रही है।",
        ],
        PA: [
            "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਜੀ, ਕੀ ਮੇਰੀ ਗੱਲ {name} ਜੀ ਨਾਲ ਹੋ ਰਹੀ ਹੈ? ਮੈਂ {lender} ਤੋਂ {agent} ਬੋਲ ਰਿਹਾ ਹਾਂ। ਤੁਹਾਨੂੰ ਦੱਸ ਦੇਵਾਂ ਕਿ ਇਹ call record ਕੀਤੀ ਜਾ ਰਹੀ ਹੈ।",
            "Hello {name} ਜੀ, ਮੈਂ {agent} ਬੋਲ ਰਿਹਾ ਹਾਂ {lender} ਵੱਲੋਂ। ਇਹ call quality ਵਾਸਤੇ record ਹੋ ਰਹੀ ਹੈ ਜੀ।",
        ],
    },
    "A_OPEN_UNDISCLOSED": {
        HI: [
            "Hello, {name} जी बोल [रहे|रही] हैं? मैं {agent} बोल रहा हूँ {lender} से, आपके loan account के बारे में बात करनी थी।",
            "नमस्ते {name} जी, {lender} से {agent} बात कर रहा हूँ। आपके {product} की payment के बारे में call किया है।",
            "हाँ जी, {name} जी? मैं {lender} से {agent} बोल रहा हूँ। दो minute बात हो सकती है?",
        ],
        PA: [
            "ਸਤ ਸ੍ਰੀ ਅਕਾਲ {name} ਜੀ, ਮੈਂ {lender} ਤੋਂ {agent} ਬੋਲ ਰਿਹਾ ਹਾਂ। ਤੁਹਾਡੇ loan account ਬਾਰੇ ਗੱਲ ਕਰਨੀ ਸੀ।",
            "Hello ਜੀ, {name} ਜੀ ਬੋਲ ਰਹੇ ਹੋ? ਮੈਂ {agent}, {lender} ਵੱਲੋਂ। ਤੁਹਾਡੀ {product} ਦੀ payment ਬਾਰੇ call ਕੀਤੀ ਹੈ।",
        ],
    },
    "B_ACK": {
        HI: [
            "हाँ जी, मैं ही बोल [रहा|रही] हूँ। बताइए।",
            "जी हाँ, बोलिए क्या बात है?",
            "हाँ, {name} ही हूँ। कहिए।",
        ],
        PA: [
            "ਹਾਂ ਜੀ, ਮੈਂ ਹੀ ਬੋਲ [ਰਿਹਾ|ਰਹੀ] ਹਾਂ। ਦੱਸੋ।",
            "ਹਾਂਜੀ, ਬੋਲੋ ਕੀ ਗੱਲ ਹੈ?",
        ],
    },
    # ------------------------------------------------------------------- dues
    "A_DUES_CORRECT": {
        HI: [
            "{name} जी, आपके {product} की {n} EMI pending हैं। Late fee मिलाकर total बकाया {due} है।",
            "[Sir|Madam], आपकी {emi} की EMI इस महीने bounce हुई है और अभी total outstanding {due} है।",
            "आपके account में {due} का overdue amount दिख रहा है, जिसमें {n} EMI और late charges शामिल हैं।",
        ],
        PA: [
            "{name} ਜੀ, ਤੁਹਾਡੇ {product} ਦੀਆਂ {n} EMI pending ਨੇ। Late fee ਮਿਲਾ ਕੇ total ਬਕਾਇਆ {due} ਹੈ।",
            "ਜੀ, ਤੁਹਾਡੇ account ਵਿੱਚ {due} ਦਾ overdue amount ਹੈ, ਜਿਸ ਵਿੱਚ {n} EMI ਤੇ late charges ਸ਼ਾਮਲ ਨੇ।",
        ],
    },
    "A_DUES_WRONG": {
        HI: [
            "{name} जी, आपके {product} पर total बकाया {wrong} है, और यह पूरा amount आज ही जमा करना होगा।",
            "आपके account में {wrong} का outstanding है [Sir|Madam], penalty और charges मिलाकर।",
            "देखिए, आपको {wrong} भरने हैं, इससे कम में account regular नहीं होगा।",
        ],
        PA: [
            "{name} ਜੀ, ਤੁਹਾਡੇ {product} ਤੇ total ਬਕਾਇਆ {wrong} ਹੈ, ਤੇ ਇਹ ਪੂਰਾ amount ਅੱਜ ਹੀ ਜਮ੍ਹਾਂ ਕਰਵਾਉਣਾ ਪਵੇਗਾ।",
            "ਤੁਹਾਡੇ account ਵਿੱਚ {wrong} ਦਾ outstanding ਹੈ ਜੀ, penalty ਤੇ charges ਮਿਲਾ ਕੇ।",
        ],
    },
    # ------------------------------------------------------ borrower responses
    "B_WILL_PAY": {
        HI: [
            "ठीक है, मैं इस Friday तक payment कर [दूँगा|दूँगी]।",
            "हाँ मुझे पता है। Salary आते ही दो-तीन दिन में भर [दूँगा|दूँगी]।",
            "अच्छा, आप link भेज दीजिए, मैं शाम तक कर [देता|देती] हूँ।",
        ],
        PA: [
            "ਠੀਕ ਹੈ ਜੀ, ਮੈਂ ਇਸ Friday ਤੱਕ payment ਕਰ [ਦੇਵਾਂਗਾ|ਦੇਵਾਂਗੀ]।",
            "ਹਾਂ ਜੀ ਮੈਨੂੰ ਪਤਾ ਹੈ। ਤਨਖਾਹ ਆਉਂਦੇ ਹੀ ਦੋ-ਤਿੰਨ ਦਿਨਾਂ ਵਿੱਚ ਭਰ [ਦੇਵਾਂਗਾ|ਦੇਵਾਂਗੀ]।",
        ],
    },
    "B_HARDSHIP": {
        HI: [
            "<sigh> देखिए, मेरी job चली गई है पिछले महीने। थोड़ा time चाहिए मुझे।",
            "<sigh> अभी बहुत tight चल रहा है, दुकान का काम मंदा है। अगले महीने तक रुक जाइए।",
            "Sir, salary दो महीने से delay हो रही है। मैं भागने [वाला|वाली] नहीं हूँ, बस थोड़ी मोहलत दे दीजिए।",
        ],
        PA: [
            "<sigh> ਦੇਖੋ ਜੀ, ਮੇਰੀ job ਚਲੀ ਗਈ ਹੈ ਪਿਛਲੇ ਮਹੀਨੇ। ਥੋੜ੍ਹਾ time ਚਾਹੀਦਾ ਹੈ ਮੈਨੂੰ।",
            "<sigh> ਹੁਣ ਹੱਥ ਬਹੁਤ ਤੰਗ ਹੈ ਜੀ, ਫ਼ਸਲ ਦੇ ਪੈਸੇ ਨਹੀਂ ਆਏ ਅਜੇ। ਅਗਲੇ ਮਹੀਨੇ ਤੱਕ ਰੁਕ ਜਾਓ।",
        ],
    },
    "B_DISPUTE": {
        HI: [
            "लेकिन मैंने तो पिछले हफ़्ते ही एक EMI भर दी थी। आपका record update नहीं है क्या?",
            "इतना कैसे हो गया? मेरे हिसाब से तो इतना amount नहीं बनता। Statement भेजिए पहले।",
        ],
        PA: [
            "ਪਰ ਮੈਂ ਤਾਂ ਪਿਛਲੇ ਹਫ਼ਤੇ ਹੀ ਇੱਕ EMI ਭਰ ਦਿੱਤੀ ਸੀ। ਤੁਹਾਡਾ record update ਨਹੀਂ ਹੋਇਆ?",
            "ਇੰਨਾ ਕਿਵੇਂ ਹੋ ਗਿਆ? ਮੇਰੇ ਹਿਸਾਬ ਨਾਲ ਤਾਂ ਇੰਨਾ amount ਨਹੀਂ ਬਣਦਾ। ਪਹਿਲਾਂ statement ਭੇਜੋ।",
        ],
    },
    "B_BEREAVEMENT": {
        HI: [
            "<sniffles> भाई साहब, परसों मेरे पिताजी का देहांत हो गया है। अभी घर में तेरहवीं चल रही है।",
            "<sigh> देखिए, मेरी माँ गुज़र गई हैं पिछले हफ़्ते। अभी मैं कुछ सोचने की हालत में नहीं हूँ।",
        ],
        PA: [
            "<sniffles> ਵੀਰ ਜੀ, ਪਰਸੋਂ ਮੇਰੇ ਪਿਤਾ ਜੀ ਪੂਰੇ ਹੋ ਗਏ ਨੇ। ਅਜੇ ਘਰ ਵਿੱਚ ਭੋਗ ਦੀ ਤਿਆਰੀ ਚੱਲ ਰਹੀ ਹੈ।",
            "<sigh> ਦੇਖੋ ਜੀ, ਮੇਰੀ ਮਾਤਾ ਜੀ ਦਾ ਪਿਛਲੇ ਹਫ਼ਤੇ ਦੇਹਾਂਤ ਹੋ ਗਿਆ ਹੈ। ਅਜੇ ਮੈਂ ਕੁਝ ਸੋਚਣ ਦੀ ਹਾਲਤ ਵਿੱਚ ਨਹੀਂ ਹਾਂ।",
        ],
    },
    "B_HOSPITAL": {
        HI: [
            "<sigh> अभी मैं hospital में हूँ, मेरे बेटे का accident हो गया है और वो ICU में है।",
            "देखिए अभी बात नहीं कर [सकता|सकती], [मेरी wife|मेरे husband] का operation चल रहा है।",
        ],
        PA: [
            "<sigh> ਮੈਂ ਹੁਣ hospital ਵਿੱਚ ਹਾਂ ਜੀ, ਮੇਰੇ ਪੁੱਤਰ ਦਾ accident ਹੋ ਗਿਆ ਹੈ, ਉਹ ICU ਵਿੱਚ ਹੈ।",
        ],
    },
    "B_WEDDING": {
        HI: [
            "देखिए, कल मेरी बेटी की शादी है, घर में मेहमान हैं। अभी यह सब बात नहीं हो सकती।",
            "अभी मेरी बहन की शादी का function चल रहा है, बारात आने वाली है।",
        ],
        PA: [
            "ਦੇਖੋ ਜੀ, ਕੱਲ੍ਹ ਮੇਰੀ ਧੀ ਦਾ ਵਿਆਹ ਹੈ, ਘਰ ਵਿੱਚ ਮਹਿਮਾਨ ਨੇ। ਹੁਣ ਇਹ ਗੱਲ ਨਹੀਂ ਹੋ ਸਕਦੀ।",
        ],
    },
    "B_PREF_TIME": {
        HI: [
            "अभी मैं duty पर हूँ, बात नहीं कर [सकता|सकती]। आप please {pt} के बाद call कीजिए।",
            "दिन में मैं shop पर busy [रहता|रहती] हूँ। मुझे {pt} के बाद ही phone किया कीजिए।",
        ],
        PA: [
            "ਹੁਣ ਮੈਂ duty ਤੇ ਹਾਂ ਜੀ, ਗੱਲ ਨਹੀਂ ਕਰ [ਸਕਦਾ|ਸਕਦੀ]। ਤੁਸੀਂ please {pt} ਤੋਂ ਬਾਅਦ call ਕਰਨਾ।",
            "ਦਿਨੇ ਮੈਂ ਖੇਤ ਵਿੱਚ busy [ਹੁੰਦਾ|ਹੁੰਦੀ] ਹਾਂ। ਮੈਨੂੰ {pt} ਤੋਂ ਬਾਅਦ ਹੀ phone ਕਰਿਆ ਕਰੋ।",
        ],
    },
    "B_ANGRY": {  # borrower loses temper: NOT an agent violation
        HI: [
            "<shouting> रोज़-रोज़ phone करके परेशान कर रखा है तुम लोगों ने! दिमाग खराब कर दिया है, चोर company है तुम्हारी!",
            "<shouting> तुम लोगों को शर्म नहीं आती? मैं consumer court में complaint कर [दूँगा|दूँगी] तुम्हारी!",
        ],
        PA: [
            "<shouting> ਰੋਜ਼-ਰੋਜ਼ phone ਕਰ ਕੇ ਤੰਗ ਕੀਤਾ ਹੋਇਆ ਹੈ ਤੁਸੀਂ ਲੋਕਾਂ ਨੇ! ਦਿਮਾਗ ਖ਼ਰਾਬ ਕਰ ਦਿੱਤਾ, ਚੋਰ company ਹੈ ਤੁਹਾਡੀ!",
        ],
    },
    "B_OFFERS_RELATIVE": {  # borrower brings up a relative: NOT a third-party violation
        HI: [
            "मेरे बड़े भाई ही सारा हिसाब देखते हैं। आप चाहें तो उनसे बात कर लीजिए, मैं number दे [देता|देती] हूँ।",
            "Payment तो [मेरी wife करती|मेरे husband करते] हैं, आप उन्हीं को बता दीजिए।",
        ],
        PA: [
            "ਮੇਰੇ ਵੱਡੇ ਭਰਾ ਹੀ ਸਾਰਾ ਹਿਸਾਬ ਦੇਖਦੇ ਨੇ। ਤੁਸੀਂ ਚਾਹੋ ਤਾਂ ਉਹਨਾਂ ਨਾਲ ਗੱਲ ਕਰ ਲਓ, ਮੈਂ number ਦੇ [ਦਿੰਦਾ|ਦਿੰਦੀ] ਹਾਂ।",
        ],
    },
    "B_PARTIAL_OFFER": {  # borrower names an amount that is not on the loan record
        HI: [
            "अभी पूरा नहीं हो पाएगा। मैं फ़िलहाल {part} दे [सकता|सकती] हूँ, बाकी अगले महीने।",
        ],
        PA: [
            "ਹੁਣ ਪੂਰਾ ਨਹੀਂ ਹੋ ਸਕਣਾ ਜੀ। ਮੈਂ ਫ਼ਿਲਹਾਲ {part} ਦੇ [ਸਕਦਾ|ਸਕਦੀ] ਹਾਂ, ਬਾਕੀ ਅਗਲੇ ਮਹੀਨੇ।",
        ],
    },
    "B_CLOSE": {
        HI: ["ठीक है, धन्यवाद।", "जी ठीक है।", "हम्म, ठीक है। Thank you।"],
        PA: ["ਠੀਕ ਹੈ ਜੀ, ਧੰਨਵਾਦ।", "ਚੰਗਾ ਜੀ, ਠੀਕ ਹੈ।"],
    },
    "B_UPSET_CLOSE": {
        HI: [
            "आप ऐसे बात नहीं कर सकते मुझसे। मैं आपकी complaint [करूँगा|करूँगी]।",
            "<sigh> please ऐसा मत कीजिए, मैं कोशिश कर [रहा|रही] हूँ।",
        ],
        PA: [
            "ਤੁਸੀਂ ਮੇਰੇ ਨਾਲ ਇਸ ਤਰ੍ਹਾਂ ਗੱਲ ਨਹੀਂ ਕਰ ਸਕਦੇ। ਮੈਂ ਤੁਹਾਡੀ complaint [ਕਰਾਂਗਾ|ਕਰਾਂਗੀ]।",
            "<sigh> please ਇਸ ਤਰ੍ਹਾਂ ਨਾ ਕਰੋ ਜੀ, ਮੈਂ ਕੋਸ਼ਿਸ਼ ਕਰ [ਰਿਹਾ|ਰਹੀ] ਹਾਂ।",
        ],
    },
    # ------------------------------------------------- compliant agent replies
    "A_POLITE_PLAN": {
        HI: [
            "कोई बात नहीं, मैं समझता हूँ। क्या आप अभी एक EMI यानी {emi} भर सकते हैं? बाकी के लिए हम date तय कर लेते हैं।",
            "ठीक है। मैं आपको payment link SMS कर देता हूँ, आप अपनी सुविधा से {due} जमा कर दीजिए।",
            "जी, आप चाहें तो part payment भी कर सकते हैं। मैं restructuring के option भी share कर देता हूँ।",
        ],
        PA: [
            "ਕੋਈ ਗੱਲ ਨਹੀਂ ਜੀ, ਮੈਂ ਸਮਝਦਾ ਹਾਂ। ਕੀ ਤੁਸੀਂ ਹੁਣ ਇੱਕ EMI ਯਾਨੀ {emi} ਭਰ ਸਕਦੇ ਹੋ? ਬਾਕੀ ਲਈ ਆਪਾਂ date ਪੱਕੀ ਕਰ ਲੈਂਦੇ ਹਾਂ।",
            "ਠੀਕ ਹੈ ਜੀ। ਮੈਂ ਤੁਹਾਨੂੰ payment link SMS ਕਰ ਦਿੰਦਾ ਹਾਂ, ਤੁਸੀਂ ਆਪਣੀ ਸਹੂਲਤ ਨਾਲ {due} ਜਮ੍ਹਾਂ ਕਰਵਾ ਦਿਓ।",
        ],
    },
    "A_DISPUTE_OK": {
        HI: [
            "जी बिल्कुल, मैं अभी आपको statement WhatsApp पर भेज देता हूँ। आप check कर लीजिए, फिर बात करते हैं।",
            "ठीक है, मैं payment record verify करवा लेता हूँ और updated statement share कर देता हूँ।",
        ],
        PA: [
            "ਜੀ ਬਿਲਕੁਲ, ਮੈਂ ਹੁਣੇ ਤੁਹਾਨੂੰ statement ਭੇਜ ਦਿੰਦਾ ਹਾਂ। ਤੁਸੀਂ check ਕਰ ਲਓ, ਫਿਰ ਗੱਲ ਕਰਦੇ ਹਾਂ।",
        ],
    },
    "A_BACKOFF": {
        HI: [
            "ओह, यह सुनकर बहुत दुख हुआ। माफ़ कीजिए, मैंने गलत समय पर call किया। आप अपना ध्यान रखिए, हम कुछ दिन बाद बात करेंगे।",
            "जी, मैं समझता हूँ। अभी आप परिवार को time दीजिए, मैं अगले हफ़्ते call करूँगा।",
            "Sorry [Sir|Madam], मुझे पता नहीं था। अभी कोई बात नहीं, आप free हो जाएँ तब बात कर लेंगे।",
        ],
        PA: [
            "ਓਹ, ਇਹ ਸੁਣ ਕੇ ਬਹੁਤ ਦੁੱਖ ਹੋਇਆ ਜੀ। ਮਾਫ਼ ਕਰਨਾ, ਮੈਂ ਗਲਤ ਵੇਲੇ call ਕਰ ਲਈ। ਤੁਸੀਂ ਆਪਣਾ ਖ਼ਿਆਲ ਰੱਖੋ, ਆਪਾਂ ਕੁਝ ਦਿਨਾਂ ਬਾਅਦ ਗੱਲ ਕਰਾਂਗੇ।",
            "ਜੀ, ਮੈਂ ਸਮਝਦਾ ਹਾਂ। ਹੁਣ ਤੁਸੀਂ ਪਰਿਵਾਰ ਨੂੰ time ਦਿਓ, ਮੈਂ ਅਗਲੇ ਹਫ਼ਤੇ call ਕਰਾਂਗਾ।",
        ],
    },
    "A_ACK_PREF": {
        HI: ["ठीक है [Sir|Madam], मैं note कर लेता हूँ। आगे से आपको {pt} के बाद ही call किया जाएगा। धन्यवाद।"],
        PA: ["ਠੀਕ ਹੈ ਜੀ, ਮੈਂ note ਕਰ ਲੈਂਦਾ ਹਾਂ। ਅੱਗੇ ਤੋਂ ਤੁਹਾਨੂੰ {pt} ਤੋਂ ਬਾਅਦ ਹੀ call ਕੀਤੀ ਜਾਵੇਗੀ। ਧੰਨਵਾਦ।"],
    },
    "A_CALM": {
        HI: ["[Sir|Madam], मैं आपकी परेशानी समझता हूँ और असुविधा के लिए माफ़ी चाहता हूँ। मैं सिर्फ़ आपकी help करना चाहता हूँ ताकि extra charges न लगें।"],
        PA: ["ਜੀ, ਮੈਂ ਤੁਹਾਡੀ ਪਰੇਸ਼ਾਨੀ ਸਮਝਦਾ ਹਾਂ ਤੇ ਤਕਲੀਫ਼ ਲਈ ਮਾਫ਼ੀ ਚਾਹੁੰਦਾ ਹਾਂ। ਮੈਂ ਸਿਰਫ਼ ਤੁਹਾਡੀ help ਕਰਨਾ ਚਾਹੁੰਦਾ ਹਾਂ ਤਾਂ ਜੋ extra charges ਨਾ ਲੱਗਣ।"],
    },
    "A_LEGAL_INFO": {  # lawful information about consequences: NOT a threat
        HI: [
            "मैं बस inform कर रहा हूँ कि delay होने पर late charges बढ़ेंगे और आपके credit score पर असर पड़ सकता है।",
            "[Sir|Madam], अगर account लंबे समय तक overdue रहा तो company नियम के अनुसार legal notice भेज सकती है। इसलिए जल्दी regular कर लेना बेहतर है।",
        ],
        PA: [
            "ਮੈਂ ਬੱਸ ਦੱਸ ਰਿਹਾ ਹਾਂ ਜੀ ਕਿ delay ਹੋਣ ਤੇ late charges ਵਧਣਗੇ ਤੇ ਤੁਹਾਡੇ credit score ਤੇ ਅਸਰ ਪੈ ਸਕਦਾ ਹੈ।",
        ],
    },
    "A_DECLINE_RELATIVE": {
        HI: ["धन्यवाद, लेकिन loan आपके नाम पर है तो हम सिर्फ़ आपसे ही बात करेंगे। आप उनसे बात करके मुझे payment की date बता दीजिए।"],
        PA: ["ਧੰਨਵਾਦ ਜੀ, ਪਰ loan ਤੁਹਾਡੇ ਨਾਮ ਤੇ ਹੈ ਤਾਂ ਅਸੀਂ ਸਿਰਫ਼ ਤੁਹਾਡੇ ਨਾਲ ਹੀ ਗੱਲ ਕਰਾਂਗੇ। ਤੁਸੀਂ ਉਹਨਾਂ ਨਾਲ ਗੱਲ ਕਰ ਕੇ ਮੈਨੂੰ payment ਦੀ date ਦੱਸ ਦਿਓ।"],
    },
    "A_ACCEPT_PARTIAL": {
        HI: ["ठीक है, {part} का part payment आज कर दीजिए। बाकी amount के लिए मैं अगले महीने की date note कर लेता हूँ।"],
        PA: ["ਠੀਕ ਹੈ ਜੀ, {part} ਦੀ part payment ਅੱਜ ਕਰ ਦਿਓ। ਬਾਕੀ amount ਲਈ ਮੈਂ ਅਗਲੇ ਮਹੀਨੇ ਦੀ date note ਕਰ ਲੈਂਦਾ ਹਾਂ।"],
    },
    "A_CLOSE": {
        HI: ["धन्यवाद {name} जी, आपका दिन शुभ हो।", "ठीक है, समय देने के लिए धन्यवाद। नमस्ते।"],
        PA: ["ਧੰਨਵਾਦ {name} ਜੀ, ਤੁਹਾਡਾ ਦਿਨ ਚੰਗਾ ਰਹੇ।", "ਠੀਕ ਹੈ ਜੀ, time ਦੇਣ ਲਈ ਧੰਨਵਾਦ। ਸਤ ਸ੍ਰੀ ਅਕਾਲ।"],
    },
    "A_HARD_CLOSE": {  # firm but lawful
        HI: ["कल तक payment हो जानी चाहिए, बस।"],
        PA: ["ਕੱਲ੍ਹ ਤੱਕ payment ਹੋ ਜਾਣੀ ਚਾਹੀਦੀ ਹੈ, ਬੱਸ।"],
    },
    # ------------------------------------------------ violating agent replies
    "A_PRESS_SENSITIVE": {
        HI: [
            "देखिए वो आपका personal मामला है, उससे company को कोई मतलब नहीं। Payment आज ही चाहिए, अभी के अभी।",
            "यह सब बहाने हम रोज़ सुनते हैं। कुछ भी हो, EMI आज शाम तक जमा होनी चाहिए।",
            "ठीक है, लेकिन पहले payment कर दीजिए, फिर जो करना है कीजिए। मैं phone नहीं रखूँगा जब तक आप pay नहीं करते।",
        ],
        PA: [
            "ਦੇਖੋ ਉਹ ਤੁਹਾਡਾ personal ਮਸਲਾ ਹੈ, company ਨੂੰ ਉਸ ਨਾਲ ਕੋਈ ਮਤਲਬ ਨਹੀਂ। Payment ਅੱਜ ਹੀ ਚਾਹੀਦੀ ਹੈ, ਹੁਣੇ ਦੀ ਹੁਣੇ।",
            "ਇਹ ਸਭ ਬਹਾਨੇ ਅਸੀਂ ਰੋਜ਼ ਸੁਣਦੇ ਹਾਂ। ਕੁਝ ਵੀ ਹੋਵੇ, EMI ਅੱਜ ਸ਼ਾਮ ਤੱਕ ਜਮ੍ਹਾਂ ਹੋਣੀ ਚਾਹੀਦੀ ਹੈ।",
        ],
    },
    "A_THREAT": {
        HI: [
            "<shouting> देखो, ज़्यादा होशियारी मत दिखाओ! कल तक पैसा नहीं आया तो हमारे लड़के घर आकर सामान उठा ले जाएँगे।",
            "<shouting> बेशर्म हो तुम लोग! Loan लेते time तो बड़ी मीठी बातें की थीं। अब पुलिस भेजकर अंदर करवा दूँगा।",
            "<shouting> तुम जैसे चोरों को हम अच्छे से जानते हैं। पैसा निकालो वरना हाथ-पैर सलामत नहीं रहेंगे।",
        ],
        PA: [
            "<shouting> ਦੇਖ, ਜ਼ਿਆਦਾ ਚਲਾਕੀ ਨਾ ਦਿਖਾ! ਕੱਲ੍ਹ ਤੱਕ ਪੈਸੇ ਨਾ ਆਏ ਤਾਂ ਸਾਡੇ ਮੁੰਡੇ ਘਰ ਆ ਕੇ ਸਮਾਨ ਚੁੱਕ ਕੇ ਲੈ ਜਾਣਗੇ।",
            "<shouting> ਬੇਸ਼ਰਮ ਬੰਦੇ ਹੋ ਤੁਸੀਂ! ਹੁਣ ਪੁਲਿਸ ਭੇਜ ਕੇ ਅੰਦਰ ਕਰਵਾ ਦਿਆਂਗਾ ਤੈਨੂੰ।",
        ],
    },
    "A_THIRD_PARTY": {
        HI: [
            "ठीक है, फिर मैं आपके office में आपके manager को call करके बताता हूँ कि आप loan नहीं भर रहे।",
            "आपके पिताजी और भाई का number भी हमारे पास है। अब उन्हीं से वसूली होगी, और मोहल्ले में भी सबको पता चलेगा।",
            "हम आपकी photo defaulter लिखकर आपके WhatsApp groups और Facebook पर डाल देंगे, फिर देखना।",
        ],
        PA: [
            "ਠੀਕ ਹੈ, ਫਿਰ ਮੈਂ ਤੁਹਾਡੇ office ਵਿੱਚ ਤੁਹਾਡੇ manager ਨੂੰ call ਕਰ ਕੇ ਦੱਸਦਾ ਹਾਂ ਕਿ ਤੁਸੀਂ loan ਨਹੀਂ ਭਰ ਰਹੇ।",
            "ਤੁਹਾਡੇ ਪਿਤਾ ਜੀ ਤੇ ਭਰਾ ਦਾ number ਵੀ ਸਾਡੇ ਕੋਲ ਹੈ। ਹੁਣ ਉਹਨਾਂ ਤੋਂ ਹੀ ਵਸੂਲੀ ਹੋਵੇਗੀ, ਤੇ ਸਾਰੇ ਪਿੰਡ ਨੂੰ ਵੀ ਪਤਾ ਲੱਗ ਜਾਵੇਗਾ।",
        ],
    },
}

# A slot that, when spoken by the agent, plants this violation at that turn.
SLOT_VIOLATION = {
    "A_OPEN_UNDISCLOSED": "NO_RECORDING_DISCLOSURE",
    "A_DUES_WRONG": "WRONG_DUES",
    "A_THREAT": "THREAT_OR_ABUSE",
    "A_THIRD_PARTY": "THIRD_PARTY",
    "A_PRESS_SENSITIVE": "IGNORED_SENSITIVE_SITUATION",
}

# (id, language, clock time, preferred window already on file, slots)
D, U = "A_OPEN_DISCLOSED", "A_OPEN_UNDISCLOSED"
OK, WRONG = "A_DUES_CORRECT", "A_DUES_WRONG"
SCENARIOS: list[tuple[str, str, str, list[str] | None, list[str]]] = [
    # ---- compliant, including the hard negatives a naive detector trips on
    ("plain_promise", HI, "11:10", None, [D, "B_ACK", OK, "B_WILL_PAY", "A_POLITE_PLAN", "B_CLOSE", "A_CLOSE"]),
    ("hardship_plan", HI, "15:30", None, [D, "B_ACK", OK, "B_HARDSHIP", "A_POLITE_PLAN", "B_CLOSE", "A_CLOSE"]),
    ("dispute_handled", HI, "10:05", None, [D, "B_ACK", OK, "B_DISPUTE", "A_DISPUTE_OK", "B_CLOSE", "A_CLOSE"]),
    ("bereavement_backoff", HI, "12:40", None, [D, "B_ACK", OK, "B_BEREAVEMENT", "A_BACKOFF", "B_CLOSE"]),
    ("angry_borrower_calm_agent", HI, "16:20", None, [D, "B_ACK", OK, "B_ANGRY", "A_CALM", "A_LEGAL_INFO", "B_CLOSE", "A_CLOSE"]),
    ("partial_offer_echoed", HI, "13:15", None, [D, "B_ACK", OK, "B_PARTIAL_OFFER", "A_ACCEPT_PARTIAL", "B_CLOSE", "A_CLOSE"]),
    ("borrower_offers_relative", HI, "17:45", None, [D, "B_ACK", OK, "B_OFFERS_RELATIVE", "A_DECLINE_RELATIVE", "B_CLOSE", "A_CLOSE"]),
    ("late_call_with_consent", HI, "19:40", ["19:00", "21:00"], [D, "B_ACK", OK, "B_WILL_PAY", "A_CLOSE"]),
    ("hardship_plan", PA, "11:30", None, [D, "B_ACK", OK, "B_HARDSHIP", "A_POLITE_PLAN", "B_CLOSE", "A_CLOSE"]),
    ("wedding_backoff", PA, "14:00", None, [D, "B_ACK", OK, "B_WEDDING", "A_BACKOFF", "B_CLOSE"]),
    ("preferred_time_captured", PA, "10:30", None, [D, "B_ACK", "B_PREF_TIME", "A_ACK_PREF", "B_CLOSE"]),
    ("preferred_time_captured", HI, "12:00", None, [D, "B_ACK", "B_PREF_TIME", "A_ACK_PREF", "B_CLOSE"]),
    ("partial_offer_echoed", PA, "16:40", None, [D, "B_ACK", OK, "B_PARTIAL_OFFER", "A_ACCEPT_PARTIAL", "B_CLOSE", "A_CLOSE"]),
    ("lawful_consequences", HI, "09:50", None, [D, "B_ACK", OK, "B_HARDSHIP", "A_LEGAL_INFO", "B_WILL_PAY", "A_CLOSE"]),
    # ---- one violation each
    ("no_disclosure", HI, "11:45", None, [U, "B_ACK", OK, "B_WILL_PAY", "A_POLITE_PLAN", "B_CLOSE", "A_CLOSE"]),
    ("inflated_dues", HI, "15:00", None, [D, "B_ACK", WRONG, "B_DISPUTE", "A_DISPUTE_OK", "B_CLOSE"]),
    ("threat", HI, "16:00", None, [D, "B_ACK", OK, "B_HARDSHIP", "A_THREAT", "B_UPSET_CLOSE"]),
    ("third_party", HI, "13:30", None, [D, "B_ACK", OK, "B_HARDSHIP", "A_THIRD_PARTY", "B_UPSET_CLOSE", "A_HARD_CLOSE"]),
    ("pressed_in_bereavement", HI, "10:50", None, [D, "B_ACK", OK, "B_BEREAVEMENT", "A_PRESS_SENSITIVE", "B_UPSET_CLOSE"]),
    ("late_call", HI, "20:35", None, [D, "B_ACK", OK, "B_WILL_PAY", "A_CLOSE"]),
    ("no_disclosure", PA, "09:15", None, [U, "B_ACK", OK, "B_HARDSHIP", "A_POLITE_PLAN", "B_CLOSE", "A_CLOSE"]),
    ("threat", PA, "17:10", None, [D, "B_ACK", OK, "B_HARDSHIP", "A_THREAT", "B_UPSET_CLOSE"]),
    ("pressed_at_wedding", HI, "18:10", None, [D, "B_ACK", OK, "B_WEDDING", "A_PRESS_SENSITIVE", "B_UPSET_CLOSE", "A_HARD_CLOSE"]),
    ("early_call", PA, "06:40", None, [D, "B_ACK", OK, "B_WILL_PAY", "A_CLOSE"]),
    ("inflated_dues_then_partial", HI, "11:00", None, [D, "B_ACK", WRONG, "B_PARTIAL_OFFER", "A_ACCEPT_PARTIAL", "B_CLOSE"]),
    ("no_disclosure", HI, "14:20", None, [U, "B_ACK", OK, "B_DISPUTE", "A_DISPUTE_OK", "B_CLOSE"]),
    ("third_party", HI, "12:50", None, [D, "B_ACK", OK, "B_DISPUTE", "A_THIRD_PARTY", "B_UPSET_CLOSE"]),
    ("threat_after_anger", PA, "15:20", None, [D, "B_ACK", OK, "B_ANGRY", "A_THREAT", "B_UPSET_CLOSE"]),
    ("pressed_in_hospital", PA, "13:05", None, [D, "B_ACK", OK, "B_HOSPITAL", "A_PRESS_SENSITIVE", "B_UPSET_CLOSE"]),
    # ---- several violations in one call
    ("everything_wrong", HI, "21:10", None, [U, "B_ACK", WRONG, "B_HARDSHIP", "A_THREAT", "B_UPSET_CLOSE"]),
    ("hospital_pressed_then_shamed", HI, "12:20", None, [D, "B_ACK", OK, "B_HOSPITAL", "A_PRESS_SENSITIVE", "B_UPSET_CLOSE", "A_THIRD_PARTY"]),
    ("inflated_dues_and_shaming", PA, "14:45", None, [D, "B_ACK", WRONG, "B_DISPUTE", "A_THIRD_PARTY", "B_UPSET_CLOSE"]),
    ("early_call_pressed_in_bereavement", PA, "07:20", None, [D, "B_ACK", OK, "B_BEREAVEMENT", "A_PRESS_SENSITIVE", "B_UPSET_CLOSE"]),
    ("no_disclosure_and_threat", HI, "15:50", None, [U, "B_ACK", OK, "B_ANGRY", "A_THREAT", "B_UPSET_CLOSE"]),
    ("no_disclosure_inflated_dues", PA, "10:10", None, [U, "B_ACK", WRONG, "B_HARDSHIP", "A_POLITE_PLAN", "B_CLOSE"]),
    ("shaming_then_threat", HI, "17:00", None, [D, "B_ACK", OK, "B_HARDSHIP", "A_THIRD_PARTY", "A_THREAT", "B_UPSET_CLOSE"]),
]

BORROWERS = {
    HI: [("राजेश", "m"), ("सुनीता", "f"), ("अमित", "m"), ("पूजा", "f"), ("विकास", "m"), ("नेहा", "f"), ("संदीप", "m"), ("कविता", "f")],
    PA: [("ਗੁਰਪ੍ਰੀਤ", "m"), ("ਮਨਪ੍ਰੀਤ", "f"), ("ਹਰਜੀਤ", "m"), ("ਸਿਮਰਨ", "f"), ("ਜਸਵਿੰਦਰ", "m"), ("ਕੁਲਦੀਪ", "m")],
}
AGENTS = {HI: ["रोहित", "अंकित", "मनोज"], PA: ["ਰਮਨ", "ਸੁਖਦੀਪ"]}  # all voiced by male Timbre voices
LENDERS = ["Suvidha Finance", "Udaan Capital", "Navjeevan Housing Finance"]
PRODUCTS = ["personal loan", "two-wheeler loan", "home loan", "business loan"]
N_WORDS = {HI: {1: "एक", 2: "दो", 3: "तीन"}, PA: {1: "ਇੱਕ", 2: "ਦੋ", 3: "ਤਿੰਨ"}}
PREF_TIMES = [  # (24h start, Hinglish phrase, Punjabi phrase)
    ("18:00", "शाम छह बजे", "ਸ਼ਾਮ ਛੇ ਵਜੇ"),
    ("19:00", "शाम सात बजे", "ਸ਼ਾਮ ਸੱਤ ਵਜੇ"),
    ("20:00", "रात आठ बजे", "ਰਾਤ ਅੱਠ ਵਜੇ"),
]

# ---- five more languages (a separate set, scored on its own): see lines_more.py
from .lines_more import (LANG_NAMES, MORE_AGENTS, MORE_BORROWERS, MORE_LINES, MORE_N_WORDS,  # noqa: E402
                         MORE_SCENARIOS)

for _lang, _slots in MORE_LINES.items():
    for _slot, _line in _slots.items():
        LINES[_slot][_lang] = [_line]
CORE_SCENARIOS = len(SCENARIOS)  # calls C01..C36 are the main benchmark
SCENARIOS += MORE_SCENARIOS
BORROWERS.update(MORE_BORROWERS)
AGENTS.update(MORE_AGENTS)
N_WORDS.update(MORE_N_WORDS)
CORE_LANGUAGES = {HI, PA}

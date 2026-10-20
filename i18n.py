"""
Translations for alerts and the SOS screen: English, Afrikaans, isiZulu, Setswana, Sesotho.

These are drafts for the safety-critical sentences only. Have a first-language speaker
review them before real use (words for "fire", "hotspot" and "emergency" vary by region).
Anything missing in a language falls back to English.
"""

LANGS = {"en": "English", "af": "Afrikaans", "zu": "isiZulu", "tn": "Setswana", "st": "Sesotho"}

T = {
    "en": {
        "alert_sms": "Firewatch: satellite detected {n} fire hotspot(s) about {km} km from {place}. "
                     "Stay alert and follow local authorities. Emergency: 112.",
        "sos_title": "Emergency alert",
        "sos_warn": "This will alert fire stations near the location below. Use it for a real fire "
                    "threatening people or property.",
        "sos_where": "Where is the emergency?",
        "sos_type": "What kind of fire?",
        "sos_address": "Street address or landmark",
        "sos_what": "What is happening? (optional)",
        "sos_name": "Your name",
        "sos_phone": "Mobile number (for call-back)",
        "sos_send": "Send SOS",
        "cancel": "Cancel",
        "done": "Done",
        "sos_sending": "Sending your alert…",
        "sos_call": "Also call 112 from a cell phone now. Move away from the fire and keep your phone on.",
        "contact_sms": "Firewatch SOS: {name} pressed the emergency button near {place}. "
                       "Please call them on {phone}. Emergency: 112.",
    },
    "af": {
        "alert_sms": "Firewatch: satelliet het {n} brandkol(le) ongeveer {km} km van {place} bespeur. "
                     "Bly waaksaam en volg die plaaslike owerhede. Nood: 112.",
        "sos_title": "Noodwaarskuwing",
        "sos_warn": "Dit waarsku brandweerstasies naby die plek hieronder. Gebruik dit net vir 'n regte "
                    "brand wat mense of eiendom bedreig.",
        "sos_where": "Waar is die noodgeval?",
        "sos_type": "Watter soort brand?",
        "sos_address": "Straatadres of landmerk",
        "sos_what": "Wat gebeur? (opsioneel)",
        "sos_name": "Jou naam",
        "sos_phone": "Selnommer (vir terugbel)",
        "sos_send": "Stuur SOS",
        "cancel": "Kanselleer",
        "done": "Klaar",
        "sos_sending": "Stuur tans jou waarskuwing…",
        "sos_call": "Bel ook nou 112 vanaf 'n selfoon. Beweeg weg van die brand en hou jou foon aan.",
        "contact_sms": "Firewatch SOS: {name} het die noodknoppie naby {place} gedruk. "
                       "Bel asseblief {phone}. Nood: 112.",
    },
    "zu": {
        "alert_sms": "Firewatch: isathelayithi ibone umlilo ongu-{n} cishe amakhilomitha angu-{km} "
                     "ukusuka e-{place}. Hlala uqaphile futhi ulandele iziphathimandla zendawo. "
                     "Isimo esiphuthumayo: 112.",
        "sos_title": "Isexwayiso sesimo esiphuthumayo",
        "sos_warn": "Lokhu kuzazisa iziteshi zomlilo eziseduze nendawo engezansi. Sebenzisa kuphela "
                    "uma umlilo ongempela usongela abantu noma impahla.",
        "sos_where": "Isimo esiphuthumayo siphi?",
        "sos_type": "Luhlobo luni lomlilo?",
        "sos_address": "Ikheli lomgwaqo noma uphawu lwendawo",
        "sos_what": "Kwenzekani? (akunyanzelekile)",
        "sos_name": "Igama lakho",
        "sos_phone": "Inombolo yocingo (yokuphinda ushayelwe)",
        "sos_send": "Thumela i-SOS",
        "cancel": "Khansela",
        "done": "Kuphelile",
        "sos_sending": "Sithumela isexwayiso sakho…",
        "sos_call": "Shayela futhi no-112 ngocingo lweselula manje. Suka emlilweni futhi ugcine ifoni ivuliwe.",
        "contact_sms": "Firewatch SOS: u-{name} ucindezele inkinobho yesimo esiphuthumayo eduze kwe-{place}. "
                       "Sicela umshayele ku-{phone}. Isimo esiphuthumayo: 112.",
    },
    "tn": {
        "alert_sms": "Firewatch: sathalaete e bone molelo o le {n} bokgakala jwa dikhilomitara di le {km} "
                     "go tswa kwa {place}. Nna o tlhokomele mme o latele balaodi ba lefelo. "
                     "Tshoganyetso: 112.",
        "sos_title": "Kitsiso ya tshoganyetso",
        "sos_warn": "Seno se tla itsise diteišene tsa molelo tse di gaufi le lefelo le le fa tlase. "
                    "Se dirise fela fa molelo wa niti o bogisa batho kana dithoto.",
        "sos_where": "Tshoganyetso e kae?",
        "sos_type": "Ke molelo wa mofuta ofe?",
        "sos_address": "Aterese ya tsela kana letshwao la lefelo",
        "sos_what": "Go diragala eng? (ga go patelesege)",
        "sos_name": "Leina la gago",
        "sos_phone": "Nomoro ya mogala (go go leletsa)",
        "sos_send": "Romela SOS",
        "cancel": "Khansela",
        "done": "Go feditse",
        "sos_sending": "Re romela kitsiso ya gago…",
        "sos_call": "Bua le 112 jaanong ka mogala wa letsogo. Tswa mo molelong mme o nne le mogala o butswe.",
        "contact_sms": "Firewatch SOS: {name} o gateletse konopo ya tshoganyetso gaufi le {place}. "
                       "Tsweetswee mo leletse mo go {phone}. Tshoganyetso: 112.",
    },
    "st": {
        "alert_sms": "Firewatch: sathalaete e bone mollo o le {n} hoo e ka bang lik'hilomithara tse {km} "
                     "ho tloha {place}. Ba hlokolosi 'me u latele ba boholong ba sebaka. "
                     "Tšohanyetso: 112.",
        "sos_title": "Temoso ea tšohanyetso",
        "sos_warn": "Sena se tla tsebisa liteishene tsa mollo tse haufi le sebaka se ka tlase. "
                    "Se sebelise feela ha ho e-na le mollo oa 'nete o ts'osang batho kapa thepa.",
        "sos_where": "Tšohanyetso e hokae?",
        "sos_type": "Ke mollo oa mofuta ofe?",
        "sos_address": "Aterese ea seterata kapa letšoao la sebaka",
        "sos_what": "Ho etsahalang? (ha ho qobelloe)",
        "sos_name": "Lebitso la hau",
        "sos_phone": "Nomoro ea mohala (ho u letsetsa)",
        "sos_send": "Romela SOS",
        "cancel": "Hlakola",
        "done": "Ho felile",
        "sos_sending": "Re romela temoso ea hau…",
        "sos_call": "Letsetsa le 112 hona joale ka mohala oa letsoho. Tloha mollong 'me u boloke mohala o bulehile.",
        "contact_sms": "Firewatch SOS: {name} o hatelletse konopo ea tšohanyetso haufi le {place}. "
                       "Ka kopo mo letsetse ho {phone}. Tšohanyetso: 112.",
    },
}


def lang_ok(code):
    return code if code in LANGS else "en"


def t(lang, key, **kw):
    text = T.get(lang_ok(lang), {}).get(key) or T["en"].get(key) or key
    try:
        return text.format(**kw) if kw else text
    except (KeyError, IndexError):
        return text

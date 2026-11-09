import random

TRIAGE = (
    "A remediation ticket names {title}, but the installed version and exposure are unconfirmed. "
    "Summarize the supplied record and any stated action without claiming this asset is affected.",
    "An analyst opened a ticket for {title}. The asset inventory is incomplete. "
    "Separate what the supplied record establishes from what would need local evidence.",
    "Triage {title} using only the supplied evidence. Do not infer affected assets "
    "or exploitation.",
    "Review the pinned record for {title}. State the documented issue and the remaining unknowns.",
)
GRAPH = (
    "The knowledge graph returned records for {title}. Explain the documented behavior and any "
    "supplied defensive measure; does this establish that the technique ran on our hosts?",
    "Using only the supplied ATT&CK evidence, describe {title} and its mitigations. "
    "Do not assert local execution or attribution.",
    "An analyst linked {title} to a hypothesis. What does the documentation support, and what "
    "would require host telemetry?",
)
CONCEPT = (
    "What is {name}?",
    "Explain {name}.",
    "Define {name} and describe why defenders care.",
    "How does {name} work?",
    "Tell me about {name}.",
    "What should a defender know about {name}?",
)
DEFENSIVE = (
    "How do defenders mitigate {name}?",
    "What documented action reduces the risk from {name}?",
    "Which mitigation applies to {name}?",
    "Explain the defensive measure supplied for {name}.",
    "What should we deploy first against {name}?",
)
SOCIAL = (
    (
        "Hello, how are you?",
        "Hello! I am here and ready to help with defensive cybersecurity questions.",
    ),
    (
        "Hi there!",
        "Hi! Ask me about vulnerabilities, ATT&CK techniques, detections or mitigations.",
    ),
    ("Thanks for your help!", "You are welcome. I am glad the analysis was useful."),
    ("Who are you?", "I am VERA, a defensive cybersecurity decision-support assistant."),
    ("Good morning", "Good morning! What defensive question can I help you with?"),
    ("Ciao, come stai?", "Hello! I am ready to help with defensive cybersecurity questions."),
    ("Okay, thank you.", "You are welcome. Tell me if you want to inspect another record."),
    (
        "Can you introduce yourself?",
        "I am VERA. I analyze supplied evidence for defensive security work.",
    ),
)
CLARIFY = (
    (
        "Can you help me with this?",
        "What would you like me to analyze? Share the question or the evidence.",
    ),
    (
        "Tell me more.",
        "More about which record or technique? Name the subject and I will focus on it.",
    ),
    (
        "What should I do next?",
        "What are you triaging? A record, an alert or a defensive control?",
    ),
    ("Is this bad?", "Which finding should I assess? I need the evidence or the identifier."),
)
LANGUAGES = {
    "Italian": (
        "Che cos'è {name}?",
        "Spiegami {name}.",
        "Come funziona {name}?",
        "Cosa dovrebbe sapere un difensore su {name}?",
    ),
    "Spanish": (
        "¿Qué es {name}?",
        "Explícame {name}.",
        "¿Cómo funciona {name}?",
    ),
    "German": (
        "Was ist {name}?",
        "Erkläre {name}.",
        "Wie funktioniert {name}?",
    ),
    "French": (
        "Qu'est-ce que {name} ?",
        "Expliquez {name}.",
        "Comment fonctionne {name} ?",
    ),
}


def pick(generator: random.Random, options: tuple[str, ...], **values) -> str:
    return generator.choice(options).format(**values)


def title_name(fragment) -> str:
    name = fragment.title.split(" | ")[0].strip()
    if " - " in name:
        name = name.split(" - ", 1)[1].strip()
    return name


def display_name(fragment) -> str:
    """Human-facing subject name; never the bare identifier."""
    title = fragment.title.strip()
    if " | " in title:
        title = title.split(" | ", 1)[1].strip()
    if " - " in title:
        title = title.split(" - ", 1)[1].strip()
    return title or title_name(fragment)

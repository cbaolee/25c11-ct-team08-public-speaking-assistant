---
topic: "AI Trends: What's Real and What's Hype"
category: "Information Technology"
duration_min: 15
---
Good {{ argument_time_of_day }}, everyone. Thank you, {{ argument_host_thanks }}, for the kind introduction. It's a pleasure to be here at {{ argument_event_name }}.

My name is {{ argument_speaker_name }}, and {{ argument_speaker_background }}

Every year, around this time, many organizations publish lists of technology trends. You've probably seen some of them: "Ten trends that will change everything," "The technologies you can't ignore." And if you go back and read those lists from five or ten years ago, you'll notice something interesting. Some predictions came true faster than anyone expected. Others are still "coming next year," every year. And some of the most important changes weren't on any list at all.

Nowhere is that more true than in artificial intelligence. So today, I don't want to give you another list of buzzwords. I'll focus on three AI trends that I believe will matter most in {{ argument_target_year }}, and for each one, I'll try to answer three honest questions. What's actually happening, beyond the marketing? What's real, and what's still hype? And what does it mean for you, whether you're a student, a developer, or someone leading a team?

At the end, I'll also give you a simple framework you can use to judge any new trend yourself, because the most valuable skill in our industry isn't knowing every new technology. It's knowing which ones deserve your attention.

Before we start, a quick show of hands, so I know who's in the room.

Trend one: from AI that answers to AI that acts.

For the past few years, most people have experienced AI as a chatbot. You ask a question, and it gives you an answer. The trend now is a shift from AI that answers to AI that acts, often called AI agents. An agent is a system built around a language model that can plan a sequence of steps, use tools such as search, code execution, or a company's internal software, check its own results, and continue until a task is done.

What's real? The underlying capabilities have improved dramatically: models are much better at following multi-step instructions, using tools, and working with long documents. Many companies are running agents in production for well-defined tasks, especially in software development, customer support, and data analysis.

What's still hype? The idea that you can hand an agent a vague goal, like "grow our sales," and walk away. My honest assessment is that {{ argument_agent_autonomy_limits }}.

Now consider a second design. The agent can look up orders and recommend a refund, but it can only issue refunds below a set amount, and only for orders that match the written refund policy, which is checked by ordinary code, not by the model. Anything outside those rules goes to a human with a summary and a recommendation. Instructions found inside customer messages are treated as data, never as commands. The second agent is slightly less impressive in a demo. But it's the one you can safely run every day.

That's the real lesson of this trend: the intelligence of the model matters, but the design of the system around it matters just as much. I would argue that {{ argument_system_design_over_model }}.

What does this mean for you? For developers, a new and valuable skill set is emerging: designing tools that agents can use safely, writing clear specifications, building evaluation suites, and handling failures gracefully. For leaders, the question isn't "Should we use agents?" It's "Which specific, measurable tasks would benefit, and what controls do we need?"

AI coding assistants have gone, in a very short time, from a novelty to a standard tool for a large share of developers. They complete code, explain unfamiliar codebases, write tests, translate between languages, and increasingly, as I just described, perform whole tasks.

What's more complicated? The evidence on overall productivity is mixed. Studies and company reports show substantial speed-ups on some tasks, but much smaller gains, or even slowdowns, on complex tasks in large, unfamiliar codebases, where reviewing and fixing AI-generated code can take as long as writing it. There are also real risks: generated code can contain subtle bugs or security vulnerabilities, can use outdated or even non-existent libraries, and can lead developers to accept code they don't fully understand.

The shift is this. Here is why I think this shift matters: {{ argument_bottleneck_shift_in_software }}.

What does good practice look like when a team uses AI to write code? A short checklist helps. First, the person who submits the code owns it, completely, whether they wrote it or an AI did. "The AI wrote it" is never an acceptable explanation for a bug. Second, AI-generated code goes through the same review and testing as any other code, with extra scrutiny on security-sensitive parts such as authentication, input handling, and database queries. Third, check every new dependency the AI suggests, because it may be outdated, unmaintained, or not exist at all, and attackers have started publishing malicious packages with names that AI tools tend to invent. And fourth, if you can't explain how a piece of code works, you're not ready to merge it.

Trend three: smaller, more efficient, and closer to the user.

Several techniques make this possible. Distillation trains a smaller model to imitate a larger one. Quantization stores the model's numbers with lower precision, which dramatically reduces memory and computation with only a modest loss in quality for many tasks. And new phones and laptops increasingly include dedicated chips for AI workloads, often called neural processing units.

Why does this matter? Four reasons. Privacy: data can stay on the device, which matters for health, finance, and personal information. Latency: responses can be instant, without a round trip to a data center. Cost: running a small model for a narrow task can be far cheaper than calling a large model for everything. And availability: it works even with a weak or no internet connection.

What's the realistic picture? My reading of the evidence is that {{ argument_small_models_realistic_value }}.

{{ argument_local_ai_adoption_example }}

Notice that these three trends are not separate. Agents need permissions to act, which makes them a security question. Coding assistants change what we expect from engineers. And smaller models are partly a response to the cost and privacy pressures that the first two trends create. The people who will be most valuable in the coming years are the ones who can see across these boundaries.

Problem: what specific problem does it solve, and for whom? If the answer is vague, like "it will transform everything," be cautious.

Proof: is anyone using it in production, at a meaningful scale, and paying for it? Demos and pilot projects are easy. Sustained use, where people choose to keep paying, is the real signal.

And price of waiting: what's the cost of waiting? For some trends, waiting is expensive, so act now. For others, it's perfectly reasonable to observe, learn, and act when the technology is more mature.

In about one minute, we've moved from "AI agents will change everything" to a much more useful conclusion: start learning and experimenting now, adopt for narrow tasks with good controls, and expand step by step as reliability is proven.

What does all this mean for each group in the room?

For developers: become the person who can make AI-assisted work reliable. That means strong review, testing, and system design skills, awareness of security and cost, and the habit of measuring whether a tool actually works for your use case.

{{ argument_speaker_closing_reflection }}

Here's my challenge. Before the end of this week, pick the trend that's most likely to affect your work or study, and take one concrete step: read one serious report, try one tool on a real task, or have one conversation with your team about what it means for you. Technology will keep changing faster than any of us can follow. The people who thrive aren't the ones who know everything. They're the ones who keep learning, deliberately, one step at a time.

Let's use the remaining time for your questions, and I'd especially like to hear which trend you think I got wrong.

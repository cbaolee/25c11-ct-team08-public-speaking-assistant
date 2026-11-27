---
topic: "AI Trends: What's Real and What's Hype"
category: "Information Technology"
duration_min: 10
---
Good {{ argument_time_of_day }}, everyone. Thank you, {{ argument_host_thanks }}, for the kind introduction. It's a pleasure to be here at {{ argument_event_name }}.

My name is {{ argument_speaker_name }}, and {{ argument_speaker_background }}

Every year, around this time, many organizations publish lists of technology trends. You've probably seen some of them: "Ten trends that will change everything," "The technologies you can't ignore." And if you go back and read those lists from five or ten years ago, you'll notice something interesting. Some predictions came true faster than anyone expected. Others are still "coming next year," every year. And some of the most important changes weren't on any list at all.

Nowhere is that more true than in artificial intelligence. So today, I don't want to give you another list of buzzwords. I'll focus on three AI trends that I believe will matter most in {{ argument_target_year }}, and for each one, I'll try to answer three honest questions. What's actually happening, beyond the marketing? What's real, and what's still hype? And what does it mean for you, whether you're a student, a developer, or someone leading a team?

A word of humility first. Trends are not prophecies. They're our best reading of the signals available today. So please treat everything I say as a hypothesis to test against your own experience, not as a certainty.

Trend one: from AI that answers to AI that acts.

What's real? The underlying capabilities have improved dramatically: models are much better at following multi-step instructions, using tools, and working with long documents. Many companies are running agents in production for well-defined tasks, especially in software development, customer support, and data analysis.

What's still hype? The idea that you can hand an agent a vague goal, like "grow our sales," and walk away. My honest assessment is that {{ argument_agent_autonomy_limits }}.

Now consider a second design. The agent can look up orders and recommend a refund, but it can only issue refunds below a set amount, and only for orders that match the written refund policy, which is checked by ordinary code, not by the model. Anything outside those rules goes to a human with a summary and a recommendation. Instructions found inside customer messages are treated as data, never as commands. The second agent is slightly less impressive in a demo. But it's the one you can safely run every day.

That's the real lesson of this trend: the intelligence of the model matters, but the design of the system around it matters just as much. I would argue that {{ argument_system_design_over_model }}.

AI coding assistants have gone, in a very short time, from a novelty to a standard tool for a large share of developers. They complete code, explain unfamiliar codebases, write tests, translate between languages, and increasingly, as I just described, perform whole tasks.

The shift is this. Here is why I think this shift matters: {{ argument_bottleneck_shift_in_software }}.

What does good practice look like when a team uses AI to write code? A short checklist helps. First, the person who submits the code owns it, completely, whether they wrote it or an AI did. "The AI wrote it" is never an acceptable explanation for a bug. Second, AI-generated code goes through the same review and testing as any other code, with extra scrutiny on security-sensitive parts such as authentication, input handling, and database queries. Third, check every new dependency the AI suggests, because it may be outdated, unmaintained, or not exist at all, and attackers have started publishing malicious packages with names that AI tools tend to invent. And fourth, if you can't explain how a piece of code works, you're not ready to merge it.

Trend three: smaller, more efficient, and closer to the user.

Why does this matter? Four reasons. Privacy: data can stay on the device, which matters for health, finance, and personal information. Latency: responses can be instant, without a round trip to a data center. Cost: running a small model for a narrow task can be far cheaper than calling a large model for everything. And availability: it works even with a weak or no internet connection.

What's the realistic picture? My reading of the evidence is that {{ argument_small_models_realistic_value }}.

{{ argument_local_ai_adoption_example }}

Now, as promised, a simple framework for judging any new trend yourself. When you hear about the next big technology, ask four questions.

Proof: is anyone using it in production, at a meaningful scale, and paying for it? Demos and pilot projects are easy. Sustained use, where people choose to keep paying, is the real signal.

Apply the four questions to AI agents. The problem: for well-defined, multi-step tasks, such as routine support requests or simple bug fixes, the answer is clear; for "running the business autonomously," it isn't. The proof: for coding assistance and customer support, there's sustained, paid use. The preconditions: reliability must keep improving, prompt injection must be managed, and organizations must build the controls and trust to delegate real actions, so broad adoption will be gradual, not sudden. And the price of waiting: for learning how agents work and experimenting on low-risk tasks, waiting is costly; for handing them high-risk, irreversible decisions, waiting is wise.

For students: the fundamentals matter more than ever. Programming, algorithms, databases, networks, and security are what allow you to understand and evaluate every new tool. Use AI to learn faster, not to avoid learning. And if you want a concrete project for the coming months, build something small but real with one of today's trends: for example, an application that uses a language model through an API, with proper input validation, error handling, and a set of test cases that measure whether it actually works. Be ready to explain not just what it does, but where it fails. That kind of project tells an employer much more than a certificate.

{{ argument_speaker_closing_reflection }}

Here's my challenge. Before the end of this week, pick the trend that's most likely to affect your work or study, and take one concrete step: read one serious report, try one tool on a real task, or have one conversation with your team about what it means for you. Technology will keep changing faster than any of us can follow. The people who thrive aren't the ones who know everything. They're the ones who keep learning, deliberately, one step at a time.

Let's use the remaining time for your questions, and I'd especially like to hear which trend you think I got wrong.

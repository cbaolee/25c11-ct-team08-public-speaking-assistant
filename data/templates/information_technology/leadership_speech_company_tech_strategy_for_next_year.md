---
topic: "Leadership Speech: Company Tech Strategy for Next Year"
category: "Technology"
duration_min: 35
---
Good {{ time_of_day }}, everyone. Thank you all for being here.

For those who don't know me yet, I'm {{ speaker_name }}, {{ speaker_role }} at {{ company_name }}. Today, I'd like to share our technology strategy for {{ strategy_year }}: where we are, where we're going, and, most importantly, why. Because a strategy only works if the people carrying it out understand the reasoning behind it, and can make good decisions on their own when the plan doesn't cover a situation, which, believe me, will happen many times this year.

I'll cover six things. First, a look back at the past year. Second, the context we're operating in. Third, the principles that will guide our technical decisions. Fourth, our strategic priorities, and just as important, what we'll stop doing. Fifth, what this means for our people and our ways of working. And sixth, how we'll measure progress. We'll have time for questions at the end, and I want to hear the hard ones.

Let's start with the past year.

I want to begin with thanks. {{ last_year_achievements }} None of that happened by accident. It happened because of the work of the people in this room, often under pressure, and often with less recognition than you deserved. So, thank you.

But I also want to look at what didn't go well, because a strategy built only on successes isn't a strategy. It's a celebration. {{ last_year_challenges }}

When I look at these challenges together, I see a pattern. {{ root_cause_reflection }} That pattern is one of the main reasons for the choices I'm going to present today.

Now, the context.

Our strategy has to respond to what's happening around us: in our market, with our customers, and in technology itself.

On the business side: {{ business_context }} Our company goals for the year are {{ company_goals }} Technology's job is to make those goals achievable, not to pursue its own agenda.

On the customer side: {{ customer_insights }}

And on the technology side, three shifts matter for us.

First, AI has moved from experiment to everyday tool. Our competitors are using it, our customers increasingly expect it, and our engineers are already using AI assistants in their daily work. The question is no longer whether we use AI, but where it creates real value for our customers, and how we use it safely and responsibly.

Second, security threats are growing in both volume and sophistication. Attackers now use AI to write convincing phishing messages and to find weaknesses faster, and attacks on the software supply chain, through the open-source components we all depend on, have become a serious risk. For a company that handles {{ sensitive_data_type }}, security isn't a technical detail. It's part of our promise to customers.

And third, efficiency matters again. After years when growth at any cost was rewarded, the expectation now is sustainable growth. That means we need to deliver more value per unit of effort, and per unit of infrastructure cost.

Now, before the priorities, the principles that will guide our technical decisions this year. I'm sharing these first because priorities tell you what we'll do, but principles tell you how to decide when you face a choice I didn't anticipate.

Principle one: customer outcomes over technical elegance. Every significant technical investment should be explainable in terms of what it does for our customers, either directly, through features and reliability, or indirectly, by making us faster or safer. If we can't explain that, we should question the investment.

Principle two: reliability and security are features. They're not things we add when we have time left. They're part of the definition of done.

Principle three: simplicity is a strategy. Every new technology, service, or tool we add has a long-term cost: someone has to learn it, maintain it, secure it, and pay for it. So we'll prefer fewer, well-understood technologies, and we'll add new ones only when the benefit is clear.

Principle four: teams own what they build, end to end. That includes its quality, its reliability, its cost, and its security, in production, not just until it's merged.

And principle five: decisions are made close to the work, with context shared widely. I'd rather have teams that understand the strategy and make good decisions quickly than a process where every decision waits for approval.

A hypothetical decision shows how these principles work, because principles only matter if they actually change what we do.

Imagine a team comes to the architecture review with a proposal: they'd like to adopt a new, very fast database for a feature they're building. The technology is impressive, and two engineers on the team are excited to learn it.

Let's apply the principles. Customer outcomes: what will customers actually get? If the honest answer is "the page will load in eighty milliseconds instead of a hundred and twenty, and users won't notice," that's a weak case. If it's "this feature is impossible to build reliably with our current database," that's a strong one. Reliability and security: who will be on call for this database at three in the morning? Do we know how to back it up, restore it, patch it, and control access to it? Simplicity: we'd be adding a new technology that the rest of the organization doesn't know. What's the long-term cost of that? Ownership: is the team willing to own it in production, fully, including its cost? And decisions close to the work: the team, which has the most context, should make the call, but with these questions answered openly.

In many cases, this conversation leads to a better option, such as using the database we already have in a smarter way. Sometimes it leads to a clear yes, with a plan for operating the new technology properly. Both outcomes are fine. What matters is that the decision is made deliberately, for the right reasons, and not just because something is new and exciting.

With those principles in mind, here are our strategic priorities for {{ strategy_year }}. There are four of them. Not ten. Four. Because if everything is a priority, nothing is.

Priority one: {{ priority_1_title }}

{{ priority_1_details }}

What this means in practice: {{ priority_1_actions }}

Priority two: {{ priority_2_title }}

{{ priority_2_details }}

What this means in practice: {{ priority_2_actions }}

Priority three: {{ priority_3_title }}

{{ priority_3_details }}

What this means in practice: {{ priority_3_actions }}

Priority four: using AI where it creates real value.

Our approach to AI, specifically, because it's an area with a lot of excitement, and a lot of risk of wasted effort.

We'll use AI in two ways. First, in our products, where it clearly improves the customer experience. {{ ai_product_plans }} Second, in our own work, to help our teams be more productive, through coding assistants, better internal search, and automation of repetitive tasks.

For both, we'll follow a few rules. We start with a real problem, not with the technology. Every AI feature must have a clear way to measure whether it works, tested before launch and monitored after. Customer data is protected: we'll only use approved tools, and we won't send sensitive data to external services without the right agreements and safeguards. A human remains accountable for any AI output that affects customers. And code written with AI help goes through the same review and testing as any other code. The person who submits it owns it.

{{ ai_governance_note }}

Now, something that's often missing from strategy presentations: what we will stop doing.

Strategy is as much about choosing what not to do as what to do. Our capacity is limited, and every project we continue takes time away from our priorities. So this year, we'll make some deliberate choices.

{{ stop_doing_list }}

I know some of these decisions will disappoint people who care about these projects. I understand that, and I respect the work that went into them. But I'd rather do fewer things well than many things poorly.

I also want to address technical debt directly, because I know it's on many of your minds. {{ tech_debt_plan }} The principle is simple: we'll treat technical debt like financial debt. Some of it is a reasonable choice that helped us move fast. But we need to know how much we have, pay the interest consciously, and pay down the parts that are costing us the most, especially where they slow down our priorities or create security and reliability risks.

A sense of how the year is likely to unfold, so you can see how the pieces fit together over time. {{ quarterly_roadmap }}

This sequencing is deliberate. We'll focus first on the foundations that make everything else easier and safer, and then build on them. If an early milestone slips, we'll adjust the later ones honestly, rather than pretending everything is still on track.

No strategy succeeds without people, which brings me to our teams and how we work.

First, structure. {{ team_structure_changes }}

Second, growth. A strategy that asks people to learn new skills has to give them time and support to do so. {{ learning_investment }} And I want to be clear about AI and jobs, because I know some of you are wondering. Our goal in using AI is to help our people do more valuable work, not to replace them. The skills that will matter most, such as understanding our customers, designing good systems, reviewing critically, and taking ownership, are exactly the skills we'll invest in.

Third, hiring. {{ hiring_plan }}

Fourth, how we work together. I've heard clearly, through {{ feedback_source }}, that {{ employee_feedback_summary }} We're going to address this by {{ ways_of_working_changes }}

And fifth, wellbeing. Ambitious goals don't mean unsustainable hours. Burned-out teams make more mistakes, build worse software, and eventually leave. If the plan requires people to work at an unsustainable pace, the plan is wrong, and I want you to tell me.

How will we know if we're succeeding?

We'll track a small set of metrics, and we'll share them openly every quarter.

For delivery, we'll look at how often we release to production, how long it takes for a change to go from code to customers, how often changes cause problems, and how quickly we recover when they do. These four measures come from many years of industry research, popularized by the DORA research program, and they're useful because they balance speed with stability. Teams that do well on them tend to deliver both faster and more reliably.

For reliability and security: {{ reliability_security_metrics }}

For our customers: {{ customer_metrics }}

And for our people: {{ people_metrics }}

An important warning about metrics. A metric is a tool for learning, not a target to game. If a team starts optimizing a number in a way that doesn't help customers, for example releasing tiny, meaningless changes just to increase deployment frequency, the metric has stopped being useful. So we'll always look at metrics together with context, and we'll never use these numbers to rank individuals.

Now, the main risks to this strategy, and how we plan to handle them. {{ strategy_risks }} We'll review this strategy every quarter, and if the world changes, or if we learn that we were wrong, we'll adjust. A strategy isn't a promise to never change your mind. It's a commitment to change it for good reasons, and to explain why.

Before we close, what all of this means for you specifically, depending on your role.

If you're an engineer: the most important thing you can do is to understand why your work matters for our priorities, and to own it end to end. Ask about the customer impact of what you're building. Treat reliability, security, and cost as part of your job. Use AI tools to work better, but stay fully responsible for the code you ship. And invest in your own growth. Take the learning time we're offering seriously.

If you're a team lead or engineering manager: your job this year is to connect the strategy to your team's daily work. Make sure every person on your team can explain how their work connects to one of our four priorities. Protect your team's focus by saying no to work that doesn't fit, and escalate when you need support in doing that. Watch for signs of burnout, and create the space for people to raise concerns early.

If you work in product or design: you're our closest link to customers, and that makes you essential to the principle of customer outcomes over technical elegance. Bring us real customer problems and evidence, involve engineers early in discussions about what to build, and help us define how we'll measure whether a feature actually worked.

And if you work in a supporting function, such as operations, security, or quality: you're the ones who help everyone else move fast safely. This year, I'd like you to focus on making the safe way the easy way, through tools, templates, and automation, rather than through more approval steps.

In summary.

Last year, we achieved a lot, and we also learned some hard lessons. This year, our context demands that we deliver more value, more efficiently, more securely, and with AI used wisely. Our principles are: customer outcomes over technical elegance, reliability and security as features, simplicity as a strategy, end-to-end ownership, and decisions close to the work. Our four priorities are {{ priorities_short_list }}, and using AI where it creates real value. We'll stop doing some things so that we can do these well. We'll invest in our people. And we'll measure our progress openly.

{{ personal_closing }}

I'd like to finish with a request. Over the next few weeks, please discuss this strategy within your teams. Ask what it means for your work. And if you see something that doesn't make sense, or a better way to reach the same goals, tell me, or tell your manager. {{ feedback_channel }} The best strategies aren't handed down. They're improved by the people who carry them out.

Now, let's open the floor. Please, ask me anything, including the difficult questions.

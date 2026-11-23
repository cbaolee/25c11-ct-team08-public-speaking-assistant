---
topic: "Ethics of Artificial Intelligence"
category: "Information Technology"
duration_min: 15
---
If an algorithm rejected your loan application, your job application, or your university application, would you have the right to know why? And who would be responsible if it got it wrong? Good {{ argument_time_of_day }}, everyone. I'm {{ argument_speaker_name }}, and {{ argument_speaker_background }} Questions like these are at the heart of today's topic: the ethics of artificial intelligence.

When people hear "AI ethics," they often imagine science fiction: robots taking over the world, or machines becoming conscious. Those are interesting questions, but they're not what I want to focus on today. I want to talk about something much more immediate: the ethical problems that AI systems are already causing, today, in real people's lives, and what those of us who build, buy, or use these systems can do about them.

Because the uncomfortable truth is this: most harms from AI don't come from evil machines or evil engineers. They come from ordinary people making reasonable-looking decisions, under deadline pressure, without asking a few important questions. My goal today is to give you those questions.

I'll structure the talk around five real cases, each illustrating a different ethical issue. Then I'll introduce the core principles that have emerged internationally, and finally, I'll give you a practical checklist you can use in your own work or study.

In 2018, Reuters reported that Amazon had stopped using an experimental AI recruiting tool. The tool had been trained on resumes submitted to the company over about ten years, most of which came from men, reflecting the gender imbalance in the tech industry. As a result, the system learned to prefer male candidates. According to the report, it penalized resumes that included the word "women's," as in "women's chess club captain." The engineers tried to correct this, but they couldn't be confident that the system wouldn't find other ways to discriminate, and the project was abandoned.

Notice what happened here. In my view, {{ argument_bias_from_history }}.

The lesson from both cases: an AI system can be accurate on average and still be unfair to specific groups. So fairness has to be measured explicitly, group by group, and not assumed.

In the United States, some courts have used risk assessment tools to help estimate how likely a defendant is to commit another crime, which can influence decisions about bail or sentencing. In 2016, the news organization ProPublica analyzed one widely used tool, called COMPAS, and reported that Black defendants who did not go on to reoffend were much more likely to be wrongly labeled as high risk than white defendants. The company that developed the tool disputed the analysis, and the debate that followed revealed something important: there are several different mathematical definitions of fairness, and in many realistic situations, it's impossible to satisfy all of them at the same time.

What this case teaches: when AI influences important decisions about people's lives, those people deserve an explanation they can understand, and a way to challenge the decision. I would argue that {{ argument_right_to_explanation }}.

The third case is about accountability and the danger of automated decisions at scale.

In the Netherlands, the tax authority used a risk classification system, along with other practices, to identify potential fraud in childcare benefits. Over several years, thousands of families were wrongly accused of fraud and ordered to repay large amounts of money, pushing many into serious financial hardship. Investigations later found, among other problems, that nationality had been used as a risk factor, and that people had very limited ability to understand or challenge the decisions. The scandal was so serious that, in January 2021, the Dutch government resigned.

The lesson: there must always be clear human accountability for decisions made with AI, and real, accessible ways for affected people to appeal.

In March 2018, in Tempe, Arizona, a self-driving test vehicle operated by Uber struck and killed a pedestrian, Elaine Herzberg, who was crossing the road with her bicycle at night. The investigation by the US National Transportation Safety Board found a combination of failures: the system detected her several seconds before the crash, but repeatedly failed to classify her correctly, partly because it hadn't been designed to expect a pedestrian crossing outside a crosswalk. Emergency braking by the system had been disabled during testing, and the human safety driver, who was supposed to intervene, was not watching the road.

Put simply, AI systems can fail in situations their designers didn't anticipate, and the real world is full of such situations. My position is that {{ argument_safety_in_unexpected_situations }}.

With generative AI, it's now possible to create realistic fake images, audio, and video of real people, commonly called deepfakes. They've been used to create non-consensual explicit images, to impersonate executives in fraud, and to spread false information during elections. At the same time, the mere existence of convincing fakes creates another problem: real evidence can be dismissed as fake. Some researchers call this the "liar's dividend."

{{ argument_local_case_example }}

Before we move to principles, I want to explain one more thing, because it's the key to preventing problems rather than just reacting to them: where, exactly, does unfairness enter an AI system? It's rarely in one obvious place. It can enter at almost every stage.

It can enter through the data, as we saw in the recruiting and facial analysis cases: some groups are underrepresented, or the data reflects past discrimination.

It can enter through proxies. Even if you remove sensitive attributes like gender or ethnicity, other features, such as a postal code, a first name, or the school someone attended, can be strongly correlated with them, and the model can learn to use them instead.

Understanding these entry points matters because it tells us that fairness isn't a single test at the end. It has to be considered at every stage, from the first conversation about what problem to solve.

In response to cases like these, many organizations have proposed principles for ethical AI. One of the most widely endorsed is the UNESCO Recommendation on the Ethics of Artificial Intelligence, adopted by UNESCO's member states in 2021. The OECD has also published AI principles that many countries have signed up to. And as I'm sure you've heard, the European Union has adopted the AI Act, which turns many of these principles into legal requirements, with stricter obligations for high-risk uses such as hiring, education, and access to essential services.

Fairness and non-discrimination. AI systems should not create or reinforce unfair discrimination, and should be tested for it.

Privacy and data protection. Personal data should be collected and used lawfully, minimally, and securely, with respect for people's rights.

Human oversight and accountability. Humans should remain responsible for AI-assisted decisions, with the ability to monitor, intervene, and correct. Someone must always be accountable.

And societal and environmental wellbeing. We should consider broader impacts, such as effects on employment, on democracy, and on the environment, given the significant energy that large AI systems can require.

Before building: What problem are we solving, and is AI really the right tool for it? Who will be affected by this system, including people who aren't our users? What could go wrong, and who would be harmed most? Could a simpler, more transparent approach work just as well?

During development and testing: How does the system perform for different groups, not just on average? How does it behave in unusual situations, and when someone deliberately tries to misuse it? Can we explain its decisions, at least to the degree needed for this use?

And after launch: Are we monitoring for errors, drift, and unexpected harms? Do we have a clear process for people to report problems? And are we willing to change or withdraw the system if it's causing harm?

Imagine a university wants to build a system that predicts which first-year students are at risk of dropping out, so that advisors can offer them support early. It sounds clearly beneficial. Let's apply the questions.

About the data: the system would likely use grades, attendance, and perhaps background information. A risk: if students from poorer regions historically dropped out more often, perhaps because they had to work part-time, the model may label any student from those regions as "high risk," even when they're doing well. That's a proxy problem.

During testing: does the model perform equally well for different groups of students? How many students does it wrongly flag as high risk, and how many does it miss?

At deployment: this is where the most important ethical decisions are made. I believe that {{ argument_deployment_ethics_choices }}.

Notice that most of the hardest questions aren't about the algorithm at all. They're about how it's used, who it affects, and who decides. The same model can be helpful or harmful, depending on those choices.

If you found questions you couldn't answer, that's completely normal. It doesn't mean the system is unethical. It means there's something worth finding out.

{{ argument_speaker_personal_reflection }}

That responsibility doesn't belong only to philosophers, regulators, or big tech companies. It belongs to every person who builds, deploys, or uses these systems. Including everyone in this room.

I'd be glad to hear your questions, and your own views, because on many of these issues, reasonable people disagree, and that's exactly why we need to talk about them.

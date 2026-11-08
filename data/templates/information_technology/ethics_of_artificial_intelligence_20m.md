---
topic: "Ethics of Artificial Intelligence"
category: "Technology"
duration_min: 20
---
If an algorithm rejected your loan application, your job application, or your university application, would you have the right to know why? And who would be responsible if it got it wrong? Good {{ argument_time_of_day }}, everyone. I'm {{ argument_speaker_name }}, and {{ argument_speaker_background }} Questions like these are at the heart of today's topic: the ethics of artificial intelligence.

When people hear "AI ethics," they often imagine science fiction: robots taking over the world, or machines becoming conscious. Those are interesting questions, but they're not what I want to focus on today. I want to talk about something much more immediate: the ethical problems that AI systems are already causing, today, in real people's lives, and what those of us who build, buy, or use these systems can do about them.

Because the uncomfortable truth is this: most harms from AI don't come from evil machines or evil engineers. They come from ordinary people making reasonable-looking decisions, under deadline pressure, without asking a few important questions. My goal today is to give you those questions.

I'll structure the talk around five real cases, each illustrating a different ethical issue. Then I'll introduce the core principles that have emerged internationally, and finally, I'll give you a practical checklist you can use in your own work or study.

Let's begin with the first case: fairness.

In 2018, Reuters reported that Amazon had stopped using an experimental AI recruiting tool. The tool had been trained on resumes submitted to the company over about ten years, most of which came from men, reflecting the gender imbalance in the tech industry. As a result, the system learned to prefer male candidates. According to the report, it penalized resumes that included the word "women's," as in "women's chess club captain." The engineers tried to correct this, but they couldn't be confident that the system wouldn't find other ways to discriminate, and the project was abandoned.

Notice what happened here. Nobody programmed the system to discriminate. The bias came from historical data, which reflected historical inequality. And the AI did exactly what it was designed to do: learn patterns from the past. The problem is that the past isn't always a pattern we want to repeat.

A second, related example comes from research. In 2018, researchers Joy Buolamwini and Timnit Gebru published a study called "Gender Shades," which evaluated commercial facial analysis systems from several major companies. They found that the systems were much less accurate at classifying the gender of darker-skinned women than of lighter-skinned men. The main reason was that the data used to build and test these systems didn't represent everyone equally. After the study was published, several of the companies improved their systems, which shows that measuring a problem openly can actually lead to change.

The lesson from both cases: an AI system can be accurate on average and still be unfair to specific groups. So fairness has to be measured explicitly, group by group, and not assumed.

The second case is about transparency and explainability.

In the United States, some courts have used risk assessment tools to help estimate how likely a defendant is to commit another crime, which can influence decisions about bail or sentencing. In 2016, the news organization ProPublica analyzed one widely used tool, called COMPAS, and reported that Black defendants who did not go on to reoffend were much more likely to be wrongly labeled as high risk than white defendants. The company that developed the tool disputed the analysis, and the debate that followed revealed something important: there are several different mathematical definitions of fairness, and in many realistic situations, it's impossible to satisfy all of them at the same time.

But there was a second problem. The tool was proprietary, so defendants couldn't fully examine how their score was calculated. Imagine being told that a computer considers you "high risk," and that this affects your freedom, but that you can't know why.

What this case teaches: when AI influences important decisions about people's lives, those people deserve an explanation they can understand, and a way to challenge the decision. And choosing what "fair" means isn't a purely technical decision. It's a value judgment that should be made openly, by the people responsible, not hidden inside a model.

The third case is about accountability and the danger of automated decisions at scale.

In the Netherlands, the tax authority used a risk classification system, along with other practices, to identify potential fraud in childcare benefits. Over several years, thousands of families were wrongly accused of fraud and ordered to repay large amounts of money, pushing many into serious financial hardship. Investigations later found, among other problems, that nationality had been used as a risk factor, and that people had very limited ability to understand or challenge the decisions. The scandal was so serious that, in January 2021, the Dutch government resigned.

This case is important because it shows how harm can multiply when an automated system is combined with rigid institutional processes, and when nobody feels responsible for questioning the results. Each person in the chain could say, "I was just following the system." That's exactly the problem.

The lesson: there must always be clear human accountability for decisions made with AI, and real, accessible ways for affected people to appeal.

The fourth case is about safety.

In March 2018, in Tempe, Arizona, a self-driving test vehicle operated by Uber struck and killed a pedestrian, Elaine Herzberg, who was crossing the road with her bicycle at night. The investigation by the US National Transportation Safety Board found a combination of failures: the system detected her several seconds before the crash, but repeatedly failed to classify her correctly, partly because it hadn't been designed to expect a pedestrian crossing outside a crosswalk. Emergency braking by the system had been disabled during testing, and the human safety driver, who was supposed to intervene, was not watching the road.

Put simply, AI systems can fail in situations their designers didn't anticipate, and the real world is full of such situations. Safety requires testing for rare and unexpected cases, multiple layers of protection, and honest thinking about how humans actually behave when they're asked to supervise automation. People are not good at staying alert when a machine does the work most of the time.

And the fifth case is about truth and manipulation.

With generative AI, it's now possible to create realistic fake images, audio, and video of real people, commonly called deepfakes. They've been used to create non-consensual explicit images, to impersonate executives in fraud, and to spread false information during elections. At the same time, the mere existence of convincing fakes creates another problem: real evidence can be dismissed as fake. Some researchers call this the "liar's dividend."

The responsibility follows directly: when we build systems that can generate realistic content, we have a responsibility to think about misuse from the start, through safeguards, clear labeling of AI-generated content, and tools that help people verify what's real.

{{ argument_local_case_example }}

Before we move to principles, I want to explain one more thing, because it's the key to preventing problems rather than just reacting to them: where, exactly, does unfairness enter an AI system? It's rarely in one obvious place. It can enter at almost every stage.

It can enter when the problem is framed. If a hospital builds a model to predict which patients need extra care, and uses past healthcare spending as a measure of need, the model will underestimate the needs of groups who historically had less access to care, and therefore spent less. A widely cited study published in Science in 2019 found exactly this kind of problem in an algorithm used for many patients in the United States.

It can enter through the data, as we saw in the recruiting and facial analysis cases: some groups are underrepresented, or the data reflects past discrimination.

It can enter through proxies. Even if you remove sensitive attributes like gender or ethnicity, other features, such as a postal code, a first name, or the school someone attended, can be strongly correlated with them, and the model can learn to use them instead.

And it can enter through feedback loops after deployment. If a system sends more inspections to certain neighborhoods, more problems will be found there, simply because more people are looking, and that new data will make the system send even more inspections there next time.

Understanding these entry points matters because it tells us that fairness isn't a single test at the end. It has to be considered at every stage, from the first conversation about what problem to solve.

Let's step back and look at these five cases together. Fairness. Transparency. Accountability. Safety. Truth. Different problems, but with some common causes: data that doesn't represent everyone, systems deployed without enough testing, decisions that can't be explained or challenged, and unclear responsibility.

In response to cases like these, many organizations have proposed principles for ethical AI. One of the most widely endorsed is the UNESCO Recommendation on the Ethics of Artificial Intelligence, adopted by UNESCO's member states in 2021. The OECD has also published AI principles that many countries have signed up to. And as I'm sure you've heard, the European Union has adopted the AI Act, which turns many of these principles into legal requirements, with stricter obligations for high-risk uses such as hiring, education, and access to essential services.

Although the wording differs, most of these frameworks share a common core. Six principles capture it.

Fairness and non-discrimination. AI systems should not create or reinforce unfair discrimination, and should be tested for it.

Transparency and explainability. People should know when they're interacting with AI, and decisions that significantly affect them should be explainable in a way they can understand.

Privacy and data protection. Personal data should be collected and used lawfully, minimally, and securely, with respect for people's rights.

Safety and robustness. Systems should work reliably, including in unexpected situations, and be protected against misuse and attacks.

Human oversight and accountability. Humans should remain responsible for AI-assisted decisions, with the ability to monitor, intervene, and correct. Someone must always be accountable.

And societal and environmental wellbeing. We should consider broader impacts, such as effects on employment, on democracy, and on the environment, given the significant energy that large AI systems can require.

Principles alone don't change much. What matters is what happens on a Tuesday afternoon, when a team is under pressure to launch. So here is a checklist of questions that anyone involved in building or deploying an AI system can ask. I'll group them by stage.

Before building: What problem are we solving, and is AI really the right tool for it? Who will be affected by this system, including people who aren't our users? What could go wrong, and who would be harmed most? Could a simpler, more transparent approach work just as well?

About the data: Where does the data come from, and did people consent to this use? Who is represented in it, and who is missing? Does it reflect historical biases that we don't want to repeat?

During development and testing: How does the system perform for different groups, not just on average? How does it behave in unusual situations, and when someone deliberately tries to misuse it? Can we explain its decisions, at least to the degree needed for this use?

At deployment: Do people know they're dealing with an AI? Can they get an explanation, and challenge a decision? Who is responsible for monitoring the system, and who has the authority to stop it if something goes wrong?

And after launch: Are we monitoring for errors, drift, and unexpected harms? Do we have a clear process for people to report problems? And are we willing to change or withdraw the system if it's causing harm?

A realistic example shows how this checklist works.

Imagine a university wants to build a system that predicts which first-year students are at risk of dropping out, so that advisors can offer them support early. It sounds clearly beneficial. Let's apply the questions.

Before building: is AI the right tool? Possibly, but the university should first check whether simple signals, like missed classes and failed first assignments, already identify most at-risk students. Who will be affected? The students, of course, but also how advisors see them.

About the data: the system would likely use grades, attendance, and perhaps background information. A risk: if students from poorer regions historically dropped out more often, perhaps because they had to work part-time, the model may label any student from those regions as "high risk," even when they're doing well. That's a proxy problem.

During testing: does the model perform equally well for different groups of students? How many students does it wrongly flag as high risk, and how many does it miss?

At deployment: this is where the most important ethical decisions are made. Is a "high risk" label used to offer extra support, or could it be used to discourage students, or affect scholarships? Do students know about the system? Can they see why they were flagged? Can an advisor ignore the prediction when they know the student better?

And after launch: is the university checking whether the support actually helps, and whether some groups are being flagged unfairly?

Notice that most of the hardest questions aren't about the algorithm at all. They're about how it's used, who it affects, and who decides. The same model can be helpful or harmful, depending on those choices.

Now, I'd like you to try this yourself for a moment.

[Reflection exercise, about one minute. Ask the audience to think of an AI system they use or are building, such as a recommendation feed, a chatbot, a grading tool, or a face unlock feature, and to choose two questions from the checklist that they can't confidently answer. Optionally, invite one or two people to share.]

If you found questions you couldn't answer, that's completely normal. It doesn't mean the system is unethical. It means there's something worth finding out.

{{ argument_speaker_personal_reflection }}

So, what can you do, starting now?

If you're a student: take the ethical and social side of computing seriously. When you build a project that uses data about people, ask the checklist questions, and write about them in your report. That habit will make you a better engineer.

If you're a developer or data scientist: measure performance across groups, document your data and models, test for misuse, and when you see a problem, raise it, clearly and early. Speaking up is part of professional responsibility.

And if you're a manager or leader: create the conditions for ethical work. Give teams time to test properly, reward people who raise concerns rather than punishing them, and make sure someone is clearly accountable for every AI system you deploy.

Let me close with a thought. AI is a tool of enormous potential. It can help diagnose diseases, make education more accessible, and help us understand our world better. But tools reflect the choices of the people who build and use them. The question isn't whether AI is good or bad. It's whether we're careful enough, honest enough, and brave enough to make it serve people fairly.

That responsibility doesn't belong only to philosophers, regulators, or big tech companies. It belongs to every person who builds, deploys, or uses these systems. Including everyone in this room.

I'd be glad to hear your questions, and your own views, because on many of these issues, reasonable people disagree, and that's exactly why we need to talk about them.

---
topic: "Estimating Tasks with Story Points"
category: "Technology"
duration_min: 10
---
Raise your hand if you've ever said "this will take two days," and it took two weeks. Keep your hand up if it happened more than once. Thank you, you can put them down now. Good {{ argument_time_of_day }}, everyone. I'm {{ argument_speaker_name }}, and today we're going to talk about something every software team struggles with: estimation. More specifically, how to estimate work using story points.

Now, a quick experiment. How long would it take you to walk from here to {{ argument_nearby_landmark }}? Think about it for a second.

I'm guessing you all came up with different answers, and most of you weren't very confident. Now, a different question: which is farther from here, {{ argument_nearby_landmark }} or {{ argument_farther_landmark }}?

That one's easy, isn't it? Almost everyone agrees immediately.

That little experiment shows the key idea behind story points. Humans are not very good at absolute estimates, like "this will take exactly fourteen hours." But we're surprisingly good at relative estimates, like "this is about twice as big as that." Story points take advantage of that.

So, what is a story point?

A story point is a unit that measures the relative size of a piece of work compared to other pieces of work. It's not hours, and it's not days. It combines three things: how much work there is, how complex it is, and how much uncertainty or risk is involved.

For example, a task that's very simple but repetitive might be a two. A task that's short but involves a tricky part of the system nobody fully understands might be a five, because of the uncertainty.

Most teams use a scale based on the Fibonacci sequence, or something close to it: one, two, three, five, eight, thirteen, and sometimes twenty or more. Why these strange numbers, instead of one to ten? Because the gaps between the numbers grow as the work gets bigger. And that reflects reality: the bigger the task, the less precise our estimate can be. It's easy to tell the difference between a one and a two. It's almost meaningless to argue about whether something is a fourteen or a fifteen. The scale forces us to admit that uncertainty.

To make story points work, a team needs a reference point. Here's how most teams start. They pick a small, well-understood story that everyone agrees on, and they call it a two or a three. Then every other story is estimated by comparing it to that one. "Is this bigger or smaller than our reference? About twice as big? Then it's around a five."

Now, how do we actually estimate as a team? The most popular technique is called planning poker. It was introduced by James Grenning and later popularized by Mike Cohn.

It works like this. Each team member has a set of cards with the numbers on our scale. The product owner reads a user story and answers questions about it. Then, everyone privately chooses a card, and all cards are revealed at the same time.

That simultaneous reveal is important. It prevents the most senior or most confident person from influencing everyone else.

If everyone shows similar numbers, great. We take that estimate and move on. But if the numbers are very different, say, one person shows a two and another shows a thirteen, that's the most valuable moment in the whole process. We ask both people to explain their thinking. Often, the person with the high number has spotted a hidden complexity, like a dependency or a tricky edge case. Or the person with the low number knows a shortcut, like an existing component we can reuse. After the discussion, we vote again. And if the numbers are still far apart after a second round, that's useful information too: it usually means the story isn't understood well enough to estimate. Instead of forcing a number, the team can split the story, write down the open questions, or schedule a short, time-boxed investigation, often called a spike, to reduce the uncertainty first. An honest "we don't know yet" is far more valuable to the people planning around your work than a confident number that turns out to be wrong.

So, the real value of planning poker isn't just the number. It's the conversation that brings hidden assumptions to the surface.

Once a team has used story points for a few sprints, it can measure its velocity: the average number of points it completes per sprint. If a team typically completes about thirty points per sprint, and the remaining work in the backlog adds up to around one hundred and twenty points, we can forecast that it will take roughly four sprints. That's a much more realistic forecast than adding up hundreds of individual hour estimates. Just remember that velocity changes when the team changes: a new member, a holiday period, or a large production incident will all lower it for a while. So forecasts should always be presented as a range, and updated every sprint, not treated as a promise made once.

Now, a warning about the most common mistakes, because story points are very easy to misuse.

The first mistake: converting points into hours. As soon as people start saying "one point equals four hours," we've lost the benefit of relative estimation and gone back to the precise guessing we're bad at.

The second: comparing velocity between teams. One team's five is not the same as another team's five. Each team has its own scale. Saying "Team A completes forty points and Team B only twenty" means nothing.

The third: using velocity as a performance target. If managers reward teams for higher velocity, teams will simply start giving bigger estimates. The numbers go up, but nothing actually gets faster. Velocity is a planning tool, not a productivity score.

And the fourth: estimating giant stories. If something is estimated at thirteen or more, it's usually a sign that it's too big and too uncertain. The right move is to split it into smaller stories.

I should also mention that story points are not the only option. Some teams use simpler t-shirt sizes, like small, medium, and large. Others skip detailed estimation altogether and simply count how many similarly sized stories they finish. What matters most is not the specific technique, but that the team has an honest, shared understanding of the work.

{{ argument_team_specific_application }}

Story points, in brief: they measure the relative size of work, combining effort, complexity, and uncertainty. We use a growing scale, like the Fibonacci sequence, because big tasks are less predictable. Planning poker helps the team estimate together and uncover hidden assumptions. Velocity helps us forecast. And we avoid turning points into hours, comparing teams, or using velocity as a target.

Estimation will never be perfect. But done well, it helps a team plan realistically, communicate honestly with stakeholders, and understand its own work much better.

Shall we try a quick round of planning poker together?

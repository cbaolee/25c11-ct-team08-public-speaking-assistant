---
topic: "Digital Addiction and Screen Time"
category: "Information Technology"
duration_min: 20
---
Hello, everyone, and thank you for coming. I'm {{ argument_speaker_name }}, and {{ argument_speaker_background }}

Before I start, I'd like to try a small experiment. Please take out your phone, but don't unlock it. Just hold it in your hand, or put it face down in front of you.

To understand Digital Addiction and Screen Time deeply—not just as a buzzword, but as an engineering tool—it helps to look at it through three lenses: the core problem it was invented to solve, how it works under the hood, and the trade-offs you accept whenever you choose to use it. Every technology in computing is a trade-off, and engineers who understand those trade-offs make far better architectural decisions than those who simply follow trends.

Now, be honest with yourself. How many of you felt a small urge, just now, to check it? To see if there's a new message, a notification, or something new in your feed?

That small urge is what I want to talk about today.

Most of us spend many hours a day looking at screens. Some of that is work or study. Some of it is genuinely valuable: talking to family, learning something new, or relaxing. But many of us also have the feeling that we spend more time on our phones than we want to, that we pick them up without thinking, and that we sometimes finish an hour of scrolling feeling worse, not better.

So today, I'd like to explore three questions. Is "digital addiction" real? Why are our devices and apps so hard to put down? And what can we, as individuals, as parents, and as people who build technology, actually do about it?

Let's start with the first question: is digital addiction real?

The answer is more nuanced than headlines suggest. My own reading is that {{ argument_is_it_really_addiction }}.

But whether or not we use the word "addiction," many people clearly experience problematic use: they use their devices more than they intend, find it hard to stop, and notice negative effects on sleep, concentration, relationships, or mood. For practical purposes, that's what matters. The question isn't "Am I clinically addicted?" It's "Is my use of technology serving my life, or getting in its way?"

It's also important to say that screen time is not one thing. An hour video-calling your grandmother, an hour learning to code, and an hour scrolling short videos at two in the morning are very different experiences. What you do, when, and how it makes you feel matters more than the total number of hours.

Now, the second question: why is it so hard to put our phones down?

Part of the answer is that many apps are deliberately designed to capture as much of our attention as possible. I would argue that {{ argument_attention_business_model }}.

A few of the most common design techniques, because once you can see them, they lose some of their power over you.

The first is variable rewards. Psychologists have long known, from experiments going back to B. F. Skinner, that unpredictable rewards are especially powerful at driving repeated behavior, more than predictable ones. When you pull down to refresh your feed, you don't know what you'll get: maybe something boring, maybe something exciting. That uncertainty, similar to a slot machine, keeps you checking.

The second is infinite scroll and autoplay. Traditionally, a newspaper or a TV episode had a natural ending, a moment where you'd decide whether to continue. Infinite feeds and automatically playing videos remove those stopping points. Aza Raskin, the designer often credited with creating infinite scroll, has since spoken publicly about regretting its effect on how much time people spend online.

The third is notifications. Each notification is designed to pull you back into the app. Red badges, sounds, and vibrations are hard to ignore, and many are triggered not because something important happened, but because the app wants you back.

And the fourth is social validation. Likes, comments, views, and streaks tap into our deep human need for approval and belonging. Waiting to see how many people liked a post can become a powerful habit loop, especially for teenagers, who are particularly sensitive to social feedback.

None of this means that the people who build these apps are villains, or that using them is wrong. Even so, I believe {{ argument_design_responsibility_balance }}.

So what are the effects? Research here is active and sometimes contested, so I'll stick to the areas where there's broader agreement.

Sleep: using screens late at night, especially with engaging content, is associated with going to sleep later and sleeping less, and poor sleep affects mood, learning, and health.

Attention: frequent switching between tasks and notifications makes deep, sustained concentration harder. Even having your phone visible on your desk can be distracting for some people.

And mental wellbeing: the relationship between social media use and mental health, especially among young people, is one of the most debated topics in current research. Some researchers argue that heavy social media use has contributed significantly to rising rates of anxiety and depression among teenagers. Others argue that the effects found in many studies are small on average, and that other factors matter more. What most agree on is that effects vary greatly between individuals, and that some kinds of use, such as passive scrolling and constant social comparison, seem more harmful than others, such as active communication with friends.

{{ argument_local_context_note }}

Before we move on to solutions, let's turn this into something personal, with a short exercise.

If you found at least one "draining" app near the top of your list, you're in very good company. Keep that app in mind for the next part.

Now, the most important question: what can we do?

For individuals, here are seven practical strategies. You don't need all of them. Pick two or three that fit your life.

Measure first. Check your phone's screen time report. Most people are surprised. Don't judge yourself. Just notice.

Turn off non-essential notifications. Keep only those from real people and truly important services. This single change makes a big difference for many people.

Make your phone less tempting. Move distracting apps off your home screen, or into a folder. Some people even switch their screen to grayscale, which makes it less visually attractive.

Create phone-free zones and times, such as the dinner table, the bedroom, or the first thirty minutes after waking up. Buying a simple alarm clock, so your phone doesn't need to sleep next to you, can be surprisingly effective.

Use friction. Log out of apps after using them, or use app timers. A few seconds of extra effort gives your conscious mind a chance to ask, "Do I really want to do this?"

Be intentional. Before you pick up your phone, ask yourself: "What am I picking it up for?" If there's no answer, put it down.

And be kind to yourself. The goal isn't zero screen time. It's a relationship with technology that you choose, rather than one that chooses for you.

For parents and teachers: lead by example, because children notice what we do more than what we say. Talk with children about how apps are designed, rather than only setting rules. Create shared family agreements, such as no phones at meals. And for young children, follow guidance from health organizations. For example, the World Health Organization's 2019 guidelines recommend no sedentary screen time for children under two, and no more than one hour a day for children aged two to four, with less being better.

{{ argument_audience_specific_note }}

And finally, for those of us who build technology, which includes many people in this room. My view is that {{ argument_builders_responsibility }}.

Let's bring it all together. Whether or not we call it addiction, problematic technology use is real, and common. It's not simply a matter of weak willpower: many apps are designed, very effectively, to capture our attention. The effects on sleep, attention, and wellbeing are worth taking seriously, even though research is still developing. And there's a lot we can do: as individuals, by making small, deliberate changes; as parents and teachers, by leading by example and talking openly; and as builders of technology, by designing products that respect people's time.

Let's trace a concrete end-to-end scenario to see how Digital Addiction and Screen Time behaves under real production conditions. When traffic is low and data is clean, almost any architecture looks fast and simple. The real test arrives when concurrency spikes, network latency fluctuates, inputs arrive malformed, or requirements change mid-project. Walking through that lifecycle step by step shows where the abstraction shines and where careful engineering discipline is required.

In production systems, three common mistakes show up repeatedly around Digital Addiction and Screen Time. The first is premature complexity: adopting heavy machinery before your scale or team size actually justifies the operational overhead. The second is ignoring failure modes and observability. If you cannot measure latency, error rates, and bottlenecks when something goes wrong at two in the morning, debugging becomes pure guesswork. The third is treating documentation and automated testing as optional extras rather than core parts of the system.

When teams scale Digital Addiction and Screen Time across larger organizations and critical workloads, security, reliability, and maintainability move to the forefront. You have to think about backward compatibility, cost efficiency at scale, clear interfaces between teams, and how new engineers can onboard safely without breaking production. Good engineering is not just making something work once; it is making something easy to operate, evolve, and trust over years.

As we wrap up, keep one practical question in mind whenever you evaluate Digital Addiction and Screen Time for your next project: what is the simplest design that satisfies today's real constraints while leaving a clean path to evolve tomorrow?

So here's my challenge for you. For the next seven days, try just one of the strategies I mentioned. Notice what changes. And at the end of the week, ask yourself one question: "Was my time well spent?"

And now, you can check your phones.

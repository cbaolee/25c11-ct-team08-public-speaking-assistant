---
topic: "Capstone / Graduation Thesis Defense"
category: "Technology"
duration_min: 45
---
Good {{ time_of_day }}, distinguished members of the committee, my supervisor, {{ supervisor_name }}, and everyone present. My name is {{ student_name }}, {{ student_details }} Today, it's my honor to present and defend my graduation thesis, titled: "{{ thesis_title }}."

Before I begin, I'd like to sincerely thank the committee for taking the time to read my thesis and to be here today, and to thank my supervisor for their guidance throughout this work.

My presentation is organized into seven parts. First, the introduction: the motivation, the problem, and the objectives of the thesis. Second, the background and related work. Third, my proposed approach. Fourth, the implementation, followed by a short demonstration. Fifth, the experiments and results. Sixth, a discussion of the limitations and the validity of the results. And finally, the conclusion and future work. After that, I'll respond to the comments in the reviewer's report, and then I'll be glad to answer your questions.

Part one: introduction.

First, the motivation behind this work.

{{ motivation }}

From this context, the specific problem my thesis addresses can be stated as follows.

{{ problem_statement }}

I'd like to emphasize why this problem is worth solving, both from a practical and a technical point of view. {{ problem_significance }}

Based on this problem, I defined the following objectives for the thesis.

{{ thesis_objectives }}

It's equally important to be clear about the scope, meaning what this thesis does and does not cover. {{ thesis_scope }} I deliberately limited the scope in this way so that, within the time available for a graduation thesis, I could solve the core problem thoroughly, with proper evaluation, rather than covering a wider area superficially.

To summarize this first part, the main contributions of my thesis are these.

{{ main_contributions }}

I'll come back to each of these contributions in the results section, and show the evidence that supports them.

Part two: background and related work.

To understand the approach I propose, there are a few key concepts I need to introduce first.

{{ background_concepts }}

Now, let's look at how other people have approached this problem. I reviewed the existing work and grouped it into a few main approaches.

{{ related_work_summary }}

When I compared these approaches, I focused on a few criteria that matter most for the problem I described: {{ comparison_criteria }}

From this comparison, I identified the following gap in existing work. {{ research_gap }}

This gap is the starting point of my thesis. In other words, my work doesn't try to replace all existing approaches. It tries to address one specific weakness, in one specific context, and to evaluate carefully whether my approach actually improves on it.

Part three: the proposed approach.

First the overall picture, then the details of each component.

{{ approach_overview }}

The key idea behind my approach is this. {{ key_idea }}

The main components deserve a closer look.

{{ component_details }}

At this point, I'd like to explain the most important design decisions, because I think the reasons behind a design are as important as the design itself.

{{ design_decisions }}

For each of these decisions, I considered alternatives. I chose based on the objectives I defined at the beginning, and on the constraints of the problem, rather than simply choosing the most popular or the newest technique. Where a choice involved a trade-off, I tried to measure its effect in the experiments, which I'll show you in part five.

Part four: implementation.

Now, how I turned this design into a working system.

{{ implementation_overview }}

The main technologies I used are {{ tech_stack }} I chose them because {{ tech_stack_reason }}

During implementation, I faced several practical challenges that weren't visible at the design stage. The most significant one was this. {{ implementation_challenge }}

To solve it, {{ implementation_solution }}

I'd also like to mention how I ensured the quality of the implementation. {{ quality_assurance }}

Before the demonstration, let me briefly describe how the work was carried out over the course of the thesis, because the process explains several of the decisions you've seen.

{{ work_process }}

Working in iterations like this was important. Each time I evaluated an early version, I discovered something I hadn't anticipated: an assumption that didn't hold, a component that was slower than expected, or a case the design didn't handle. Rather than waiting until the end to find these problems, I could adjust the design while there was still time. Several of the design decisions I explained earlier were, in fact, the result of these early evaluations, not of my initial plan.

I also kept a record of the experiments and changes throughout the project, including the configuration used for each experiment and the results obtained. This made it possible to reproduce every result reported in the thesis, and to trace each number in the results chapter back to a specific version of the code and data. {{ reproducibility_note }}

Now, I'd like to show you a short demonstration of the system, so you can see how it works in practice.

[Live demonstration, about five minutes. Suggested order: the main scenario from start to finish, then the feature that best shows the thesis's contribution, then one difficult or edge case. Prepare a recorded video as a backup in case of technical problems.]

Thank you. As you can see, the system supports the full scenario I described in the problem statement. Now, of course, a working demonstration shows that the system functions. It doesn't yet show that it's better, or how well it performs. For that, we need systematic experiments, which brings me to the next part.

Part five: experiments and results.

First, the experimental setup, because the results are only meaningful if the setup is clear and fair.

The data I used is as follows. {{ dataset_description }}

To evaluate the results, I used these metrics. {{ evaluation_metrics }} I chose these metrics because they directly reflect the objectives of the thesis. A metric is only useful if it measures what we actually care about.

To know whether my approach is actually an improvement, I compared it with the following baselines. {{ baselines }}

And the experimental environment was: {{ experimental_environment }}

To make the comparison fair, all methods were evaluated on the same data, with the same metrics, and in the same environment. Where results could vary between runs, I repeated the experiments several times and reported the average, so that a single lucky or unlucky run wouldn't distort the conclusions.

Now, the main results.

{{ main_results }}

What matters is what these results mean, not just the numbers.

{{ results_interpretation }}

I also wanted to understand which parts of my approach contribute most to the results. So I ran an additional experiment, removing or changing one component at a time and observing the effect. This is sometimes called an ablation study.

{{ ablation_or_component_analysis }}

This analysis is important, because it shows that the improvement comes from the ideas proposed in this thesis, and not simply from other factors such as more data or more computing power.

I'd also like to show a case where my approach did not perform well, because I believe failures are just as informative as successes.

{{ failure_case_analysis }}

Now, connecting the results back to the objectives I set at the beginning. {{ objectives_achievement }}

Part six: discussion, limitations, and validity.

No research work is complete without a discussion of its limitations. So I'll address them directly.

First, the limitations of the approach and the system themselves. {{ limitations }}

Second, I'd like to discuss the validity of the results, which means: how much can we trust the conclusions, and how far can they be generalized?

There are three types of concerns I considered.

The first concerns whether the experiments truly measured what I intended. For example, if there were a mistake in the implementation of a baseline, or if the test data had accidentally overlapped with data used during development, the comparison would be unfair. To reduce this risk, {{ internal_validity_measures }}

The second concerns generalization: whether the results would hold in other contexts. My experiments were conducted on specific data and in a specific environment. The results may be different with other data, at a larger scale, or with other users. So my conclusions should be understood within the scope I defined, and I've avoided claiming more than the evidence supports.

And the third concerns the metrics themselves: whether they fully capture what matters in practice. Metrics simplify reality. A system can score well on a metric and still be difficult to use, or fail in situations the metric doesn't capture. That's one reason I complemented the numbers with qualitative analysis, such as the failure case I just showed.

Being aware of these limitations doesn't weaken the contributions of the thesis. Rather, it defines precisely where the results are reliable, and it points directly to the most valuable future work.

Part seven: conclusion and future work.

Looking back over the whole thesis, what has it done?

I started from a real problem: {{ problem_short }} I reviewed existing approaches and identified a specific gap. I proposed an approach based on the key idea of {{ key_idea_short }} I implemented it as a working system, and evaluated it experimentally against established baselines, with a fair and transparent setup.

The results show that {{ conclusion_results }}

In terms of contributions, this thesis has: {{ contributions_recap }}

For future work, I see several promising directions. {{ future_work }}

On a personal note, {{ personal_reflection }}

That concludes the main presentation. Thank you very much for your attention.

Now, before your questions, I'd like to respond to the comments in the reviewer's report. I'm very grateful to the reviewer, {{ reviewer_name }}, for reading my thesis so carefully. The comments helped me see my work more clearly, and I've taken each of them seriously.

{{ reviewer_comments_responses }}

For comments that I've already addressed, the changes are included in the revised version of the thesis. For those that require more extensive work, I've included them in the future work section, and I'd be glad to discuss them further with the committee.

I'm now ready to answer the committee's questions.

[Committee questions. The following prepared answers cover questions that committees frequently ask. Use them as needed, adapting them to the exact question. Answer briefly and directly first, then explain. If you don't know an answer, say so plainly, and explain how you would find out.]

[If asked: "What is your main contribution, in one sentence?"]

In one sentence: {{ one_sentence_contribution }}

[If asked: "Why didn't you use a different method or technology?"]

That's a very good question. When choosing my approach, I considered several alternatives, including {{ alternatives_considered }} I chose my approach mainly because it best fit the objectives and constraints of this problem. That said, I think the alternative you mention would be an interesting direction to compare in future work, and I'd be happy to hear your thoughts on it.

[If asked: "How do you know your results are reliable?"]

I tried to ensure reliability in three ways. First, all methods were compared under the same conditions, on the same data, with the same metrics. Second, I repeated experiments where results could vary, and reported averages. And third, I analyzed not only the overall numbers, but also individual components and failure cases. However, as I mentioned in the validity discussion, the results are limited to the data and environment I tested, so I would be careful about generalizing them further without additional experiments.

[If asked: "Can this be applied in practice?"]

{{ practical_application_answer }}

[If asked: "What was the most difficult part of your thesis?"]

{{ hardest_part_answer }}

[If asked: "Which parts did you build yourself, and which parts come from existing libraries or prior work?"]

It's important to be precise about this. {{ own_work_vs_existing }} All the existing libraries, datasets, and prior methods I used are cited in the thesis, and the comparison in the results chapter is between my contributions and those existing methods, under the same conditions.

[If asked: "How would your system perform at a much larger scale?"]

In the current experiments, the system was tested at the scale I described in the setup. At a much larger scale, I'd expect the main pressure points to be {{ scalability_bottlenecks }} I haven't tested at that scale, so I can't claim it would work without changes. But the design separates the components clearly, so the parts most likely to become bottlenecks could be optimized or replaced without redesigning the whole system. Testing at a larger scale is one of the first things I'd do in future work.

[If asked: "Are there any ethical, privacy, or security concerns with your work?"]

{{ ethics_privacy_answer }} More generally, I believe any system that processes real users' data should collect only what it needs, protect what it stores, and be transparent with users about how their data is used. Those principles guided my choices, and they would need even more attention in a real deployment.

[If asked: "If you started this thesis again, what would you do differently?"]

{{ do_differently_answer }} Looking back, I think the most valuable lesson is to evaluate early and often. The earlier I tested my ideas against real data, the faster I learned what actually worked.

[If asked a question you cannot answer:]

That's a question I haven't studied in enough depth to give you a confident answer. My understanding is limited to what I've explained, but I think it's an important point, and I'll look into it further. Could I ask what direction you would suggest?

[After the final question:]

Thank you very much to all members of the committee for your questions and valuable feedback. I'll carefully consider all your comments to improve my thesis. And once again, thank you to my supervisor, my family, and my friends for their support throughout this journey.

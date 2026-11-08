---
topic: "Becoming a Data Analyst from Zero"
category: "Technology"
duration_min: 18
---
Imagine a coffee chain with twenty shops. The manager asks: "Sales dropped last month. Why?" One person might guess: "Maybe it was the rain." Another might say: "Maybe customers don't like the new menu." A data analyst doesn't guess. They look at the sales data by shop, by day, by product, and by time of day. And they might find something like this: sales dropped mainly in three shops near universities, mainly in the afternoon, starting the week the students' exam period ended. In other words, it's not the menu and it's not the rain. It's the semester break. And that leads to a very different decision.

That's the essence of data analysis: turning raw data into clear answers that help people make better decisions.

Hi everyone. I'm {{ speaker_name }}, and {{ speaker_background }} Today, I'll show you how someone can go from zero to a first job as a data analyst: what the job really is, what skills you need, a step-by-step plan, and how to prove your skills to employers, even if you've never worked with data before.

What does a data analyst actually do? A typical week might include talking with managers to understand their questions, collecting and cleaning data from databases or spreadsheets, analyzing it to find trends and patterns, building charts and dashboards, and presenting findings with clear recommendations. Data analysts work in almost every industry: retail, banking, e-commerce, healthcare, logistics, marketing, and the public sector.

And here's some good news for career changers. Data analysis is one of the most accessible entry points into the tech industry. You don't need a computer science degree. Many successful analysts come from business, economics, finance, marketing, or even teaching. In fact, knowledge of a business area can be a real advantage.

So, what skills do you need? I'd group them into five.

First, spreadsheets. Excel or Google Sheets are still the most widely used analysis tools in the business world. You need to be comfortable with formulas, lookups, cleaning data, and especially pivot tables, which let you summarize large amounts of data in seconds.

Second, SQL. This is the most important technical skill for a data analyst. Most company data lives in databases, and SQL is how you ask questions of those databases. You should be able to select and filter data, join tables, group and aggregate, and eventually use more advanced features like window functions, which let you calculate things like running totals and rankings.

Third, statistics. Not advanced theory, but solid basics: averages and medians, and when to use which; spread and variation; percentages and growth rates; the idea of sampling; correlation, and why it doesn't prove causation; and the basic logic of comparing two groups, as in A/B testing.

Fourth, data visualization and dashboard tools, such as Power BI, Tableau, or Looker Studio. More importantly than any tool, you need to learn how to choose the right chart for the message, and how to make it clear and honest.

And fifth, the skill that ties everything together: business thinking and communication. Understanding what question really matters, what decision depends on the answer, and how to explain your findings to people who don't care about formulas. An analysis that nobody understands is an analysis that changes nothing.

Later, you can add Python, especially the pandas library, for automating analysis and handling larger or messier datasets. It's very valuable, but for a first analyst role, strong SQL and spreadsheets usually matter more.

To make this more concrete, let's go back to the coffee chain from the beginning and walk through how an analyst would actually solve that problem, step by step.

Step one: clarify the question. "Sales dropped" is too vague. So the analyst asks the manager: dropped compared to what? Last month or the same month last year? Revenue or number of orders? All shops or some shops? Let's say the answer is: revenue fell by twelve percent compared to the previous month, across the whole chain.

Step two: get the data. The analyst writes an SQL query to pull every transaction from the last two months, with the shop, date, time, product, and amount. Then they check the data quality: are any days missing? Are there duplicate transactions? Did any shop close for renovation? It turns out one shop was closed for three days, which is noted, but it doesn't explain a twelve percent drop.

Step three: break it down. Using a pivot table or a few SQL queries with grouping, the analyst splits revenue by shop. Most shops are roughly stable, but three shops dropped by more than forty percent. Then they split those three shops by time of day: mornings are normal, but afternoons collapsed. Then by product: the biggest drop is in iced drinks and snacks, the kind of products students buy while studying.

Step four: find the explanation. All three shops are next to universities. The analyst checks the academic calendar and finds that the semester ended in the second week of the month. The timing matches perfectly. To confirm, the analyst looks at last year's data, and sees the same pattern at the same time of year.

Step five: recommend and communicate. The analyst prepares a one-page summary with one clear chart. The message: the drop is mostly seasonal, caused by the university break, and it's expected to recover when the semester starts. The recommendations: reduce afternoon staff in those three shops during university breaks, adjust stock to avoid waste, and perhaps test a promotion aimed at local residents during that period. And next year, include the academic calendar in the sales forecast.

Notice what happened. No advanced algorithms. Just clear questions, clean data, systematic breakdowns, and good communication. That's what most real data analysis looks like, and it's why this skill set is so valuable to businesses.

Now, a step-by-step plan. It assumes around ten to fifteen hours of study per week, and it takes about six to nine months.

Month one: spreadsheets and data thinking. Learn the key functions: sums and averages with conditions, lookups, text and date functions, and pivot tables. Practice cleaning messy data: removing duplicates, fixing inconsistent spellings, and handling missing values. At the same time, start building the habit of asking good questions. Whenever you see a number, ask: compared to what? Over what time period? Broken down by what?

Months two and three: SQL. This is where you should invest the most time. Install a free database, such as PostgreSQL, or use one of the many online practice platforms. Start with simple queries, then joins, then aggregations, and then window functions. Practice with realistic datasets, like sales, customers, and orders, and with realistic questions: Who are our top ten customers? What's the monthly revenue trend? Which products are often bought together? Aim to write SQL every single day, even for twenty minutes.

Month four: statistics and visualization. Review the basic statistics concepts I mentioned, with practical examples. Then choose one visualization tool, ideally the one most common in job postings near you, and learn to build a complete dashboard: clean the data, create a few key metrics, choose appropriate charts, and add filters. Study good examples, and learn the basic principles: start axes at zero for bar charts, avoid 3D effects and unnecessary decoration, use color with purpose, and put the most important number where people look first.

Month five: storytelling and business context. Practice turning an analysis into a short presentation. A simple structure that works very well is: here's the question; here's what we found; here's why it matters; and here's what we recommend. Practice explaining your findings in one minute, as if you were speaking to a busy manager. And choose one industry you're interested in, and learn its key metrics. For e-commerce, that might be conversion rate and average order value. For a subscription business, churn and customer lifetime value.

Month six and beyond: portfolio projects and Python. Build three portfolio projects, which I'll talk about in a moment. And, if you have time, start learning Python with pandas.

The portfolio is how you prove your skills without work experience, so it deserves real care.

A strong data analyst portfolio usually has three projects, each showing a different skill, and each telling a story rather than just showing charts.

Project one: a spreadsheet or dashboard project. For example, analyze a public dataset about something you care about: air quality in your city, football statistics, movie ratings, or public health data. Build a dashboard and write a short summary of the three most interesting findings.

Project two: an SQL project. Use a realistic business dataset, for example, a sample e-commerce dataset, and answer ten business questions with SQL. Show your queries, explain your reasoning, and present the results clearly.

Project three: an end-to-end business case. Start from a business question, clean and analyze the data, build visualizations, and finish with specific recommendations. For example: "Which customers is this online store most at risk of losing, and what should it do about it?" This project shows employers that you don't just process data. You help people decide.

For every project, write a short report or presentation that explains the question, the data, your method, your findings, and the limitations. Mentioning limitations, like missing data or a small sample, is a sign of maturity, and interviewers notice it.

Where can you find data? Many governments publish open data. International organizations publish datasets on health, economics, and development. And there are well-known data science community websites with thousands of free datasets. Just make sure you understand where the data comes from and how reliable it is.

Next, let's talk about getting your first job.

Look for roles with titles like data analyst, business analyst, reporting analyst, business intelligence analyst, or marketing analyst. Read the requirements carefully, and focus on the skills that appear most often.

Prepare for typical interview stages: a conversation about your background and motivation; a technical test, often SQL questions or an Excel task; and sometimes a case study, where you're given a dataset and asked to find insights and present them. Practice all three.

And if you're currently working in another field, look for opportunities to use data in your current job. Can you build a report that saves your team time? Can you analyze customer feedback? Many analysts made their first move internally, because their company already trusted them and saw what they could do.

{{ local_job_market_note }}

Now, a few mistakes to avoid.

First, collecting certificates instead of building projects. Courses are useful, but employers want to see what you can do.

Second, focusing only on tools and forgetting the question. The best analysts start with the business problem, not with the software.

Third, making charts that look impressive but are hard to read. Clarity beats decoration every time.

Fourth, presenting numbers without a recommendation. Always answer the question "So what?"

And fifth, giving up during the first difficult weeks of SQL. Almost everyone finds joins confusing at first. Keep practicing. One day it suddenly clicks.

And a quick word on AI. AI tools can now write SQL, suggest charts, and summarize data. They can make you much faster, and you should learn to use them. But they can also produce queries that run perfectly and return the wrong answer, for example, by joining tables incorrectly and counting some orders twice. If you understand SQL and statistics yourself, you'll catch these mistakes. If you don't, you'll confidently present wrong numbers to your manager. So learn the fundamentals first, and then let AI make you faster.

Four questions that beginners often ask.

"Excel or Python: which should I learn first?" Excel or Google Sheets first, then SQL, then Python. Spreadsheets teach you to think about data in tables and give you quick results. SQL is what you'll use every day to get data. Python becomes valuable once you need to automate repetitive work or handle data that's too large or messy for spreadsheets.

"Power BI or Tableau?" Both are excellent, and the concepts are very similar. Check which one appears more often in job postings where you want to work, and learn that one first. Once you know one well, switching to the other takes weeks, not months.

"Isn't the data analyst market already crowded?" There's certainly more competition for entry-level roles than a few years ago. But there's also a lot of demand for analysts who combine solid technical skills with business understanding and clear communication. The candidates who stand out are those with real, well-explained projects, and often with knowledge of a specific industry.

"What's the difference between a data analyst and a data scientist?" In simple terms, a data analyst mainly answers questions about what happened and why, using SQL, spreadsheets, statistics, and dashboards. A data scientist more often builds predictive models and works with machine learning, which requires deeper mathematics and programming. Many data scientists started as analysts, so the analyst role can be a great first step if you're aiming further.

The essentials: a data analyst turns data into clear answers that support decisions. The core skills are spreadsheets, SQL, basic statistics, visualization, and business communication, with Python as a valuable next step. A realistic plan takes around six to nine months of consistent study. Build three strong portfolio projects that tell stories and end with recommendations. And prepare for SQL tests and case studies in interviews.

You don't need to be a math genius to become a data analyst. You need curiosity, patience, and the habit of asking "why?" until you find a real answer.

Start this week: pick one public dataset, and write down three questions it could answer.

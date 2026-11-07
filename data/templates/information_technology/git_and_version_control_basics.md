---
topic: "Git and Version Control Basics"
category: "Technology"
duration_min: 10
---
Hi everyone, I'm {{ speaker_name }}, and today's topic is Git: a tool you'll use almost every day as a developer, and one that will probably save you from disaster more than once.

Picture a folder on your desktop. Inside it, there's a file called "report." Next to it, "report final." Then "report final version two." Then "report final version two, really final." And, of course, "report final version two, really final, fixed."

If that folder looks familiar, you're in the right room. We laugh at it, but it's a real problem. Which version is the latest? What changed between them? What if two people edited the same file at the same time? And what if you break something and need to go back to yesterday's version?

That's the problem version control solves. A version control system records changes to your files over time, so you can see who changed what, when, and why, go back to any earlier version, and let many people work on the same project without overwriting each other's work.

Git is by far the most popular version control system in the world. It was created in two thousand and five by Linus Torvalds, the creator of Linux, to manage the development of the Linux kernel, one of the largest collaborative software projects ever. Today, it's used by almost every software company, from tiny startups to the largest tech companies.

One important thing about Git is that it's distributed. Every developer has a complete copy of the project and its entire history on their own computer. That means you can work offline, and if a server fails, the history isn't lost.

Four key ideas carry most of the weight.

The first is the repository, often shortened to "repo." A repository is simply a project folder that Git is tracking, including the full history of every change. You create one with the command git init, or you copy an existing one with git clone.

The second idea is the commit. A commit is a snapshot of your project at a specific moment. It's like a save point in a video game. Each commit stores what changed, who made the change, when, and a short message explaining why. Each commit also gets a unique ID, a long string of letters and numbers called a hash.

This is the part that confuses many beginners: Git has three areas.

The working directory is where you actually edit your files. The staging area is like a waiting room, where you put the changes you want to include in your next commit. And the repository is where commits are permanently stored.

Why do we need the staging area? Because it lets you choose exactly what goes into each commit. Imagine you fixed a bug and also changed some styling. Those are two separate ideas, so you can stage and commit the bug fix first, and the styling change separately. That makes your history much clearer.

In practice, the basic cycle looks like this. You edit your files. You run git status to see what has changed. You run git add to move the changes you want into the staging area. And you run git commit with a message to save the snapshot. Edit, add, commit. You'll repeat this cycle many times a day.

The third key idea is branches. A branch is an independent line of development. Suppose your application is working well, and you want to build a new login feature. Instead of changing the main code directly, you create a new branch, maybe called "login-feature." You can experiment freely there. If it goes badly, you simply delete the branch, and the main code is untouched. If it goes well, you merge it back into the main branch.

This is what allows a team of developers to work on ten different features at the same time without getting in each other's way.

Sometimes, when you merge, Git finds that two people changed the same lines of the same file in different ways. Git can't guess which version is correct, so it asks you to decide. This is called a merge conflict. It sounds scary the first time, but it's actually quite simple: Git marks the conflicting parts in the file, you choose what the final version should be, and then you commit the result. The best way to avoid painful conflicts is to commit and merge small changes often, instead of working alone on a branch for weeks.

The fourth key idea is remotes. So far, everything has happened on your own computer. A remote is a copy of the repository hosted somewhere else, usually on a platform like GitHub, GitLab, or Bitbucket.

And this is a good moment to clear up a common confusion: Git and GitHub are not the same thing. Git is the version control tool that runs on your computer. GitHub is a website that hosts Git repositories and adds features for collaboration, like pull requests, code reviews, and issue tracking. A simple analogy: Git is like your camera, and GitHub is like a shared online photo album.

To work with remotes, there are two essential commands. git push sends your commits from your computer to the remote. And git pull brings other people's new commits from the remote down to your computer.

Put together, a typical day for a developer on a team might look like this. In the morning, you pull the latest changes. You create a branch for your task. You edit, add, and commit in small steps. You push your branch to GitHub and open a pull request, asking teammates to review your code. After the review, your branch is merged into the main branch. And the cycle begins again.

Four good habits will make you a much better teammate.

Commit small and often. One commit should represent one logical change. Small commits are easier to understand, review, and undo.

Write meaningful commit messages. "Fix stuff" or "update" tells nobody anything. "Fix crash when the cart is empty" tells your team exactly what happened. A good message completes the sentence: "If applied, this commit will..."

Pull before you start working, so you're always building on the latest version.

And never commit secrets like passwords or API keys. Once something is in Git history, it's very hard to fully remove, especially after it has been pushed. Use a file called dot gitignore to tell Git which files it should never track.

{{ team_or_class_context }}

The whole talk in a few lines: version control records the history of your project, so you can collaborate safely and go back in time when needed. Git is the most widely used version control system, and it's distributed. The core cycle is edit, add, commit. Branches let you work on features in isolation and merge them later. And remotes, like GitHub, let teams share their work with push and pull.

Learning Git can feel confusing at first, but after a couple of weeks of daily use, it becomes second nature. And one day, when you accidentally delete half your project, you'll be very, very glad you used it.

Your first commit is waiting. Make it a small one.

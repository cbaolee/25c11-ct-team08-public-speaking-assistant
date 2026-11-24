---
topic: "Docker and Containers for Beginners"
category: "Information Technology"
duration_min: 5
---
"But it works on my machine." Raise your hand if you've ever heard that sentence, or said it yourself. Yes, I see a lot of hands, and a few guilty smiles.

Good {{ argument_time_of_day }}, everyone, and welcome to {{ argument_workshop_name }}. I'm {{ argument_speaker_name }}, and I'll be your guide today as we take our first steps into the world of containers and Docker.

That sentence is one of the oldest jokes in software development, and it's exactly the problem Docker was created to solve. That's where we'll start.

Containers solve this by packaging the application together with everything it needs to run. In my view, {{ argument_why_containers_won }}.

Software containers do the same thing. Whatever is inside, a Python web app, a Java service, a database, the container looks the same from the outside, so any machine running Docker can handle it.

So where does Docker fit in?

Containers as a concept existed before Docker, using features built into the Linux kernel. I would argue that {{ argument_docker_made_containers_usable }}.

The first line says: FROM python, version three point twelve, slim. This means: start from an existing image that already has Python installed. We don't build everything from scratch; we build on top of others' work.

One important detail: each instruction in a Dockerfile creates a layer, and Docker caches these layers. It's also the reason we copy and install the requirements before copying the rest of the code. Our code changes often, but our list of libraries changes rarely. With this order, when we edit the code and rebuild, Docker reuses the cached layer with all the installed libraries, and the build takes seconds instead of minutes.

docker ps lists the containers that are currently running.

Volumes are about data. My advice rests on one belief: {{ argument_disposable_containers_mindset }}.

And when you need to run hundreds or thousands of containers across many servers in production, you'll eventually hear about Kubernetes, a system that automatically schedules, scales, and restarts containers. That's a topic for another day, but it's good to know that everything you learn today is the foundation for it.

Containers do come with a few things to watch out for. My view is that {{ argument_container_security_caution }}.

Now it's time to stop listening and start doing. {{ argument_hands_on_activity_instructions }}

Don't worry about making mistakes. Containers are disposable, so if something breaks, you can simply delete it and start again. That's one of the best things about them.

Before you dive in, is there anything I should clear up first?

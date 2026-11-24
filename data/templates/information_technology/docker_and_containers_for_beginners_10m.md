---
topic: "Docker and Containers for Beginners"
category: "Information Technology"
duration_min: 10
---
"But it works on my machine." Raise your hand if you've ever heard that sentence, or said it yourself. Yes, I see a lot of hands, and a few guilty smiles.

Good {{ argument_time_of_day }}, everyone, and welcome to {{ argument_workshop_name }}. I'm {{ argument_speaker_name }}, and I'll be your guide today as we take our first steps into the world of containers and Docker.

That sentence is one of the oldest jokes in software development, and it's exactly the problem Docker was created to solve. That's where we'll start.

Why do we need containers?

The application itself didn't change. What changed was the environment around it: the operating system, the language runtime, the libraries, the settings. And setting up that environment by hand, again and again, on every machine, is slow and full of mistakes.

Containers solve this by packaging the application together with everything it needs to run. In my view, {{ argument_why_containers_won }}.

Software containers do the same thing. Whatever is inside, a Python web app, a Java service, a database, the container looks the same from the outside, so any machine running Docker can handle it.

A virtual machine pretends to be a complete computer. It runs its own full operating system on top of your real one, with the help of software called a hypervisor. That means each virtual machine includes an entire operating system, which can take gigabytes of space and a minute or more to start.

A housing analogy captures the difference. Virtual machines are like separate houses, each with its own foundation, plumbing, and electricity. Containers are like apartments in the same building: each one is private and has its own space, but they share the foundation and the main utilities.

So where does Docker fit in?

Containers as a concept existed before Docker, using features built into the Linux kernel. I would argue that {{ argument_docker_made_containers_usable }}.

First, an image. An image is a read-only template that contains everything needed to run an application: the code, the runtime, the libraries, and the settings. Think of it as a recipe, or, if you're a programmer, as a class.

Second, a container. A container is a running instance of an image. If the image is the recipe, the container is the dish you actually cooked. Or, in programming terms, if the image is the class, the container is the object. And just as you can create many objects from one class, you can run many containers from the same image.

The first line says: FROM python, version three point twelve, slim. This means: start from an existing image that already has Python installed. We don't build everything from scratch; we build on top of others' work.

Then: COPY requirements dot txt, and RUN pip install. This copies the list of libraries our app needs and installs them.

And finally: CMD python app dot py. This is the command that runs when the container starts.

One important detail: each instruction in a Dockerfile creates a layer, and Docker caches these layers. It's also the reason we copy and install the requirements before copying the rest of the code. Our code changes often, but our list of libraries changes rarely. With this order, when we edit the code and rebuild, Docker reuses the cached layer with all the installed libraries, and the build takes seconds instead of minutes.

A handful of basic commands ties these pieces together. You'll practice all of these later today, so for now, just get familiar with them.

docker run creates and starts a container from an image. For example, "docker run nginx" downloads the official Nginx web server image, if you don't have it yet, and starts it.

docker ps lists the containers that are currently running.

And docker images lists the images stored on your machine.

By default, a container is isolated, including its network. If your web app inside the container listens on port five thousand, your browser can't reach it until you connect a port on your machine to that port in the container. That's called port mapping. With the dash p option, you can say, for example, "connect port eight thousand on my laptop to port five thousand in the container."

Volumes are about data. My advice rests on one belief: {{ argument_disposable_containers_mindset }}.

And when you need to run hundreds or thousands of containers across many servers in production, you'll eventually hear about Kubernetes, a system that automatically schedules, scales, and restarts containers. That's a topic for another day, but it's good to know that everything you learn today is the foundation for it.

Consistency: the same image runs the same way everywhere. Speed: containers start in seconds. Efficiency: they use far fewer resources than virtual machines, so you can run many more on the same hardware. Isolation: each application has its own dependencies, so two apps needing different versions of the same library can live happily side by side. And easier onboarding and deployment, because the environment is defined in code, not in someone's memory.

Containers do come with a few things to watch out for. My view is that {{ argument_container_security_caution }}.

A quick recap of the key ideas from this introduction.

Now it's time to stop listening and start doing. {{ argument_hands_on_activity_instructions }}

Don't worry about making mistakes. Containers are disposable, so if something breaks, you can simply delete it and start again. That's one of the best things about them.

Before you dive in, is there anything I should clear up first?

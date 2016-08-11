This was a test task from one famous company.

# In two words: 
It is a simple, highly available cluster chat system made by me in three days from scratch. (Without using any frameworks: there is no asyncio, no tornado, etc. There was used only pure socket API).

# Features:
Each server can be shut down or started at any time. There is enough only one running server to chat system functioning properly.
Clients are connected and automatically reconnected to the least loaded available server.

# Usage:
At first you need to prepare servers list. All servers and all clients should have this pre-established list before start. Just write it into the "server_list.txt" file. There is "server_list.txt" example file in the repository.

###Server:
* To run single instance - run "server.py" script. You may provide one integer console parameter (number of address from "server_list.txt" file - starting from zero. For example: "server.py 42"). Otherwise it will be prompted by script (of course list of addresses with their numbers will be printed to console).
* You may use local_server_pool_launcher.py script to automatically launch bunch of servers with all possible addresses from "server_list.txt" file

###Client:
* To run single instance - run "client.py" script.
* You may use local_client_pool_launcher.py script to automatically launch as many client instances as will be provided by one single integer console parameter. For example: "local_client_pool_launcher.py 321".

# Requirements (for both server and client):
**Linux** (with at least 2.5.44 kernel, and glibs of at least 2.3.2 version: chat system is using **epoll** for an async IO); **CPython 3.5+**

# Original task with comments:
_Actually I don't see why should I share it: purpose of this system and requirements are clear anyway._

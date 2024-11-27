# This project has MIT License to our team.
Name: Tuan Khai Tran, Li Jiahao
Organization: California State University, Los Angeles
Course: CS 4470 - Fall 2024
Professor: Zilong Ye
# CS4470-Assignment2-RouterApp

## Main file / program is named 'dv.py'
this program contain only one file listed above, all other files are just for testing / building purposes.

## Can be used on up to 4 separated computer
4 computer can act as 4 independent routers.
text file 'server1_init.txt' to 'server2_init.txt' are topology files for each computer with pre-set nodes, connections / edges, and cost with format:

<num-servers>
<num-neighbors>
<server-ID> <server-IP> <server-port>
<server-ID1> <server-ID2> <cost>
 
num-servers: total number of servers in the network.
num-neighbors: the number of directly linked neighbors of the server.
server-ID, server-ID1, server-ID2: a unique identifier for a server, which is assigned by you.

e.g. 'server1_init.txt'
4                           <num-servers>
3                           <num-neighbors>
1 192.168.1.8 4091          <server-ID> <server-IP> <server-port>
2 192.168.1.11 4092
3 192.168.1.50 4093
4 192.168.1.44 4094
1 2 7                       <server-ID1> <server-ID2> <cost>
1 3 4
1 4 5

#Text file edit before use:
before you run the program, make sure that you have you specific computer's IP and port number you desire to use.
double check the edge and cost, please note that the cost is bi-directional edge 1 - 3 will be equal to edge 3 - 1.

#To run program:
simply run the dv.py file with either your code editor / IDE
in my case, just hit run on VSCode and choose python compiler.
or can just run it in terminal by 'python <directory>\dv.py'
or cd to the code directory and type command 'python dv.py'

it will then prompt you to enter the server command, which is:
server -t <topology-text-file> -i <interval-message-time>
it the best to have the topology file in the same directory with .py file, when type command, don't forget '.txt'
interval message time will be sleep time between message sent.

enjoy!

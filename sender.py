# z5087077 Ka Wing Ho 
# Sample packet is a list of : [ "TYPE" , SEQNUM, ACKNUM, "DATA"]
# Types are same as the ones used in the sample log files

# Packets pending ACK are stored in a dict indexed by their expected corresponding ACK number
# They are placed in there once sent and only popped off once the respective ACK is received
# When fast retransmit occurs just sort the dict and send the pakcet in first index
# When timeout occurs just send the packet in the last index

# References used : 
# (use of pickle to serialize data) -> https://stackoverflow.com/questions/24423162/how-to-send-an-array-over-a-socket-in-python/24424025#24424025
# (initialized dictionaries) -> https://stackoverflow.com/questions/7280644/is-it-possible-in-python-to-update-or-initialize-a-dictionary-key-with-a-singl

import socket, sys, time, re, random, pickle, glob
from collections import defaultdict

#Function that writes to log
#<snd/rcv/drop> <time> <type of packet> <seq-number> <number-of-bytes> <ack-number>
def writeLog(action,type,seqNum,ackNum,dataLen,outfile):
	now = float((time.time() - start)*100) #in ms
	str="%s\t%.2f\t%s\t%d\t%d\t%d\n" % (action, now, type, seqNum, dataLen, ackNum)
	outfile.write(str)
	sys.stdout.write(str)

#Function that writes a summary string to log
def writeSummary(str,outfile):
	outfile.write(str)
	sys.stdout.write(str)

#PLD Module : return 0 for FALSE, return 1 for YES
#def toDrop(packet,pdrop):

    #Important packets will be ignored
	#if (getType(packet) != "D"): return 0

	#Drop if result <= pdrop
	#if (random.random() > pdrop): return 0
	#else: return 1  #CHANGE BACK TO 1 later

#PLD Module : return value for numDropped (0 for none,1 for one)
def toDrop(packet,pdrop,serverSocket,outfile):


	#Forward control packets and any packet with higher value than pdrop
	if (random.random() > pdrop) or (getType(packet) != "D"):
		writeLog("snd", getType(packet), getSeq(packet), getACK(packet), len(getData(packet)), outfile)
		serverSocket.sendto(pickle.dumps(packet),(receiver_ip,receiver_port))
		return 0

	else:
		print >> sys.stderr, "Dropping packet ... %d" % getSeq(packet)
		writeLog("drop", getType(packet), getSeq(packet), getACK(packet), len(getData(packet)), outfile)
		return 1



#Reads bytes from the file and puts it into a string
def readBytes(bytes,file):
	str = file.read(bytes)

	if (str is None) or (str == ""): str = ""; print >> sys.stderr, "!--EOF--!"
	return str

def getType(packet): return packet[0]
def getSeq(packet) : return packet[1]
def getACK(packet) : return packet[2]
def getData(packet): return packet[3]

def createPacket(type, seqNum, ackNum, data): return [type, seqNum, ackNum, data]

if len(sys.argv) !=9:
	print >> sys.stderr, 'Usage: python', sys.argv[0],' <receiver_host_ip> <receiver_port> <file> <MWS> <MSS> <timeout> <pdrop> <seed>'; exit()
	
receiver_ip   = sys.argv[1]
receiver_port = int(sys.argv[2])
MWS           = int(sys.argv[4])
MSS           = int(sys.argv[5])
timeout       = float(float(sys.argv[6]) * 0.001) #convert 100ms into 0.1s (eg)
pdrop         = float(sys.argv[7])
random.seed( int(sys.argv[8]) )

#Catch errors in command line arguments
if len(glob.glob(str(sys.argv[3]))) == 0: print >> sys.stderr, 'The file you specified doesn\'t exist !'   ; exit()
if pdrop < 0 or pdrop > 1:                print >> sys.stderr, 'pdrop must be between 0 and 1'             ; exit()
if timeout <= 0:                          print >> sys.stderr, 'Timeout value should be greater than zero' ; exit()
if MSS <= 0 or MSS <= 0:                  print >> sys.stderr, 'MWS and MSS must both be greater than zero'; exit()
if MSS > MWS:                             print >> sys.stderr, 'MWS must be greater than MSS'              ; exit()

try:
	#Open files for reading/writing
	f = open(sys.argv[3],'r')
	outfile = open("Sender_log.txt",'w+')

	#Set up port and binding (Socket timeout depends on value of retransmission timeout)
	serverSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	serverSocket.bind(('', 0)) #OS will choose a random free port

	if timeout < 10: socketTimeout = float(timeout/5.0)
	else: socketTimeout = float(timeout/20.0)
	if socketTimeout < 0.0005: socketTimeout = 0.0005
	serverSocket.settimeout(socketTimeout)
	
	print "Server active at port %d with timeout of %.5fs / %.2fms" % (serverSocket.getsockname()[1], timeout, timeout*1000)
except Exception as e: print str(e); exit()

#Flags, vars and dicts
start = time.time()      #Global time start for logging
TIMER_STOP   = 9999      #To simulate the timer being paused, since this value won't be reached the timeout won't happen
TIMER_RESUME = timeout   #Reenable the timer
FINACK_RECEIVED = 0      #Flag to control when to break and stop sending data
FIN_SENT        = 0      #Flag to show when FIN segment has been sent
currentSeqNum   = 0      #Current sequence number (of sender's packets)
sendBase        = 0      #Largest ACK received so far
timer = time.time()      #Default value for timeout timer
pending = {}             #Dictionary of sent packets pending acknowledgement (key: expected ACK value)
ackCount = defaultdict(int)   #Dictionary (init. to 0) that counts number of duplicate ACKS received

#Summary info
dataSent = 0
segmentsSent = 0
dupACK = 0
numDropped = 0
numRetransmit = 0

#####################################
initialSeq = random.randint(200,5000)
initialSeq = 1000
#####################################

#Send initial SYN packet to start three-way handshake
print "Sending initial SYN with sequence number %d ..." % initialSeq
packet = createPacket("S",initialSeq,0,"")
pending[initialSeq+1] = packet
writeLog("snd", "S", initialSeq, 0, 0, outfile)
serverSocket.sendto(pickle.dumps(packet),(receiver_ip,receiver_port))


'''
Minor efficiency issue: All data has been transferred (want to send FIN but can't)
because many packets were dropped and awaiting retransmission (but dropped again!)
'''


while(1):

	#print >> sys.stderr, "========================================================="  #to show new cycle
	###############################
	#PART ONE: RETRANSMISSION TIMER 
    ###############################

	timeoutCheck = time.time() - timer
	if(FINACK_RECEIVED == 0) and (timeoutCheck > timeout):
		#Resend the smallest unacknowledged packet
		if len(pending) == 0: print >> sys.stderr, "Nothing to retransmit!"; continue
		smallestKey = sorted(pending)[0]
		resend = pending[smallestKey]
		print "Packet type is %s" % getType(resend)
		assert getType(resend) == "D"
		print >> sys.stderr, 'Timeout ... resending packet %d' % getSeq(resend)
		numRetransmit = numRetransmit+1

		#Retransmissions have to go through the PLD Module as well
		numDropped = numDropped + toDrop(resend,pdrop,serverSocket,outfile)

		timer = time.time()  #reset the timer
		continue


	#############################################
	#PART TWO: PROCESS ALL INCOMING PACKETS FIRST
	#############################################
	while(len(pending) > 0):

		try:
			string, client = serverSocket.recvfrom(1024)
			packet = pickle.loads(string)
			print "BUFFER: " + str(pending.keys())
		except Exception as e: break
		#Extract info from received packet
		type = getType(packet)
		seqNum = getSeq(packet)
		ackNum = getACK(packet)
		data = getData(packet)
		reply = ""
		#Log received packet
		writeLog("rcv", type, seqNum, ackNum, len(data), outfile)


		#Send out final ACK 
		if(type == "FA"):
			if ackNum in pending: del pending[ackNum]
			FINACK_RECEIVED = 1
			seqNum = seqNum+1
			finalACK = createPacket("A", currentSeqNum, seqNum, "")
			writeLog("snd", "A", getSeq(finalACK), getACK(finalACK), len(getData(finalACK)), outfile)
			serverSocket.sendto(pickle.dumps(finalACK),(receiver_ip,receiver_port))
			currentSeqNum = currentSeqNum+1

		#Complete the handshake
		if(type == "SA"):
			sendBase = ackNum
			currentSeqNum = initialSeq+1
			seqNum = seqNum+1
			#Send ACK
			ack = createPacket("A", currentSeqNum, seqNum, "")
			writeLog("snd", "A", getSeq(ack), getACK(ack), 0, outfile)
			serverSocket.sendto(pickle.dumps(ack),(receiver_ip,receiver_port))

		#All packets at this point will be ACKs
		if(type == "A") or (type == "SA"):

			ackCount[ackNum] = ackCount[ackNum] + 1    #Add one to the ackCount of this ACK
			#if ackNum in pending: del pending[ackNum]  #ACKed segments can be removed from pending
			for unacked in pending.keys():			   #ACKed segments can be removed from pending
				if(unacked <= ackNum): del pending[unacked]

			if(ackNum > sendBase):
				sendBase = ackNum
				if(any(pending)): timer = time.time()  #reset timer
				else: timeout = TIMER_STOP             #stop timer

			elif(ackCount[ackNum] > 3):
				#fast retransmit : send the packet with sequence number matching the dupACK
				for key in pending:
					found = 0
					if( getSeq(pending[key]) == ackNum): found = key; break;

				assert (found > 0)
				retransmit = pending[found]
				numRetransmit = numRetransmit+1
				print >> sys.stderr, "Fast-retransmit of %d" % getSeq(retransmit)
				numDropped = numDropped + toDrop(retransmit,pdrop,serverSocket,outfile)


	###################################
	#PART THREE: SEND WINDOW OF PACKETS 
	###################################
	
	#Break out of loop after receiving final ACK from receiver
	if(FINACK_RECEIVED == 1): break

	#Initial check to see if receiver is active
	try: seqNum 
	except NameError: print "\n\nWait wait wait ... the receiver isn't active!\n"; exit()

	#Write and send until window is full then loop around and wait for next set of ACKs
	while(currentSeqNum - sendBase < MWS):
		print "currSeqNum is %d, sendBase is %d" % (currentSeqNum, sendBase)
		if (timeout == TIMER_STOP): timeout = TIMER_RESUME
		sendData = readBytes(MSS, f)

		#If sendData is empty string, send "F" packet
		if (sendData is None or sendData == ""):

			#If the buffer isn't empty just loop again and wait for ACKs
			if len(pending) == 0:
				print "SENDING FIN"
				FIN_SENT = 1
				reply = createPacket("F", currentSeqNum, seqNum+len(data), "")
				currentSeqNum = currentSeqNum + 1
				pending[currentSeqNum] = reply
				timer = time.time()
			else: 
				print >> sys.stderr, "Oops~can't send the FIN yet!: %s" % str(pending.keys())
				break

		#else send normal Data
		else:
			reply = createPacket("D", currentSeqNum, seqNum+len(data), sendData)
			currentSeqNum = currentSeqNum + len(sendData)
			pending[currentSeqNum] = reply
			segmentsSent = segmentsSent+1


		if reply != "":

			dataSent = dataSent + len(getData(reply))

			#Send packet to PLD Module
			numDropped = numDropped + toDrop(reply,pdrop,serverSocket,outfile)
			if(getType(reply) == "F"): break

#===ENDOFLOOP===

print >> sys.stderr, "Saving summary ... "

summary = 'Amount of (original) Data Transferred: %d bytes\n' % dataSent; writeSummary(summary, outfile)
summary = 'Number of Data Segments Sent (excluding retransmissions): %d\n' % segmentsSent; writeSummary(summary, outfile)
summary = 'Number of Packets Dropped: %d\n' % numDropped; writeSummary(summary, outfile)
summary = 'Number of Retransmitted Segments: %d\n' % numRetransmit; writeSummary(summary, outfile)

# number of duplicate acks received
for val in ackCount.keys(): dupACK = dupACK + (ackCount[val]-1)

summary = 'Number of Duplicate Acknowledgements received: %d\n' % dupACK; writeSummary(summary, outfile)



print >> sys.stderr, "Closing socket"; serverSocket.close()
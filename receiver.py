# z5087077 Ka Wing Ho 
# Sample packet is a list of : [ "TYPE" , SEQNUM, ACKNUM, "DATA"]
# Types are same as the ones used in the sample log files

import socket, sys, time, re, pickle, random

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

#Write received data into file   
def writeBytes(data,file): file.write(data)

def getType(packet): return packet[0]
def getSeq(packet) : return packet[1]
def getACK(packet) : return packet[2]
def getData(packet): return packet[3]

def createPacket(type, seqNum, ackNum, data): return [type, seqNum, ackNum, data]


if len(sys.argv) !=3:
	print >> sys.stderr, 'Usage: python', sys.argv[0],' <receiver_port> <file>'; exit();
	
try:
	#Open a file if it doesn't exist or truncate the entire file if it does
   	f = open(sys.argv[2], 'w+')
   	outfile = open("Receiver_log.txt",'w+')

	#Set up port and binding
	clientSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	clientSocket.bind(('',int(sys.argv[1])))
	print "Receiver active on port: %d" % clientSocket.getsockname()[1]

except Exception as e: print str(e); exit();


#Flags, vars and dicts
FINACK_SENT = 0  #Flag to control when to break and stop sending data
currSeqNum  = 0  #Current sequence number (of receiver's packets)
expectedSeq = 0  #Expected sequence number of inbound packet
bufferSeq   = 0  #Used in buffer to check for in-order packets to write
pending = {}     #Dictionary of received (out-of-order) packets that haven't been written yet

#Summary info
numSegments  = 0
dataReceived = 0
dupSegments  = 0

#####################################
initialSeq = random.randint(200,5000)
initialSeq = 200
#####################################


while(1):
	#############################################
    #PART ONE: RECEIVING AND CHUCKING INTO BUFFER
    #############################################
	string, sender_address = clientSocket.recvfrom(4096)
	packet = pickle.loads(string)

	#Check if packet exists in buffer and discard if necessary
	type = getType(packet)
	if(type == "S"): start = time.time() #Logfile timing starts here
	seqNum = getSeq(packet)
	ackNum = getACK(packet)
	data   = getData(packet)

	#Check for duplicate packet (by the seq num) (Should I check dup for control packets as well ? eg. FIN)
	if(pending.has_key(seqNum)) or (seqNum < expectedSeq):
		#Add to dup packets and discard
		print >> sys.stderr, "Duplicate packet received: %d" % seqNum
		dupSegments = dupSegments+1
		continue
	else:
		#Ignore FIN segment while pending buffer is non-empty
		if(type == "F") and len(pending) > 0:
			print >> sys.stderr, "Dropping FIN because buffer is non-empty: %s" % str(pending.keys())
			continue

		#Log received packets and chuck all data packets into the buffer
		if(type == "D"):
			pending[seqNum] = data
			numSegments = numSegments+1
			dataReceived = dataReceived + len(data)
			print >> sys.stderr, "Pending-buffer :" + str(pending.keys())
		writeLog("rcv", type, seqNum, ackNum, len(data), outfile)

	########################################
	#PART TWO: INSPECTING BUFFER AND WRITING
	########################################

	#expectedSeq number and ACK value are increased based on data packets written
	#print >> sys.stderr, "expectedSeq is: %d, bufferSeq is %d" % (expectedSeq,bufferSeq)
	while(pending.has_key(bufferSeq)):
		print >> sys.stderr, "Written and popped from buffer: %d, **%s**" % (bufferSeq,pending[bufferSeq])
		writeData = pending[bufferSeq]
		writeBytes(writeData,f)
		del pending[bufferSeq]
		bufferSeq = bufferSeq + len(writeData)


		if(expectedSeq < bufferSeq): 
			#print >> sys.stderr, "expectedSeq before: %d" % expectedSeq
			expectedSeq = bufferSeq  #experimental
			#print >> sys.stderr, "expectedSeq after : %d" % expectedSeq

	############################
	#PART THREE: SENDING REPLIES
	############################
	reply = ""

	#Server Sent a Final ACK
	if(type == "A") and (FINACK_SENT == 1): 
		print >> sys.stderr, "Pending-buffer: %s" % str(pending.keys())
		break;

	#If its SYN send SYNACK
	if(type == "S"): 
		reply = createPacket("SA", initialSeq, seqNum+1,"")
		expectedSeq = seqNum+1
		bufferSeq = seqNum+1
		currSeqNum = initialSeq+1

	#If its FIN send FINACK, set FINACK_SENT to 1 
	if(type == "F"): 
		if FINACK_SENT == 1: continue
		FINACK_SENT = 1
		reply = createPacket("FA",currSeqNum,seqNum+1,"")
		currSeqNum = currSeqNum+1

	#If its Data send ACK / out-of-order data resend expectedSeq
	if(type == "D"): 
		if(seqNum != expectedSeq): reply = createPacket("A",currSeqNum,expectedSeq,"")
		else: reply = createPacket("A",currSeqNum,seqNum+len(data),"")

	#Send the reply back to the server
	if reply != "":
		#Write to log and send
		writeLog("snd", getType(reply), getSeq(reply), getACK(reply), 0, outfile)
		clientSocket.sendto(pickle.dumps(reply),sender_address)

#===ENDOFLOOP===

print >> sys.stderr, "Saving summary ... "

summary = 'Amount of (original) Data Received: %d bytes\n' % dataReceived; writeSummary(summary, outfile)
summary = 'Number of Data Segments Received (excluding duplicates): %d\n' % numSegments; writeSummary(summary, outfile)
summary = 'Number of Duplicate Segments Received: %d\n' % dupSegments; writeSummary(summary, outfile)

print >> sys.stderr, "Closing socket"; clientSocket.close()
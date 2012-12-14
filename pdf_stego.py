#!/usr/bin/python
import os
import sys
import re
import select
import hashlib
import optparse

#
#
#
# CLASSES
#

# Handle PDF files
class PDF_file:

	file_name = ''

	def __init__(self,file_name):
		self.file_name = file_name

	# Generates QDF file "<file>.qdf" from PDF file "<file>", uncompressing streams if needed
	def uncompress(self):
		os.system('qpdf '+self.file_name+' '+self.file_name+'.qdf --qdf --stream-data=uncompress')

	# Generates fixed QDF  file "<file>.fix" from damaged QDF file "<file>", reconstructing XRef and trailer if needed
	def fix(self):
		os.system('fix-qdf <'+self.file_name+' >'+self.file_name+'.fix')

	# Generates PDF file "<file>.pdf" from QDF or PDF file "<file>", compressing streams if needed
	def compress(self):
		os.system('qpdf '+self.file_name+' '+self.file_name+'.pdf --stream-data=compress')

# Handle 015 and 116 numeral integers, and binary strings, and other stuff
class Numerals:

	# The number of bit to use
	n = 4

	def __init__(self,nbits):
		self.n = nbits

	def pad_binstr(self,b,nbits):
		while b.__len__() < nbits:
			b = "0" + b
		return b

	def num_to_binstr(self,num,nbits):
		return self.pad_binstr(bin(num)[2:],nbits)

	# Encodes a string into a binary string based on the ASCII codes (e.g. "a" returns "01100001")
	def str_to_binstr(self,str):
		if str.__len__() < 1:
			return ""
		else:
			result = ""
			for c in str:
				result += self.num_to_binstr(ord(c),8)
			return result

	# Encodes a 4-bit number (passed-in as a binary string, e.g. "0110") into a character
	def binstr_to_ch(self,str):
		return chr(int(str,2) % 256)

	# Encodes an ASCII code (passed-in as an hexadecimal string) into a numeral using mod(2^n)
	def hexstr_to_num(self,h):
		return int(h,16) % (2**self.n)

	# Encodes a n-bit number (passed-in as a binary string, e.g. "0110" if n is 4) into a numeral (a "015" numeral if n is 4)
	def binstr_to_num(self,str):
		return int(str,2) % (2**self.n)

	# Splits a sequence into a list of sequences of specified length (the last one may be shorter)
	def split_len(self,seq,length):
		return [seq[i:i+length] for i in range(0,len(seq),length)]

	# Returns the 20-byte SHA1 digest of a string as an hexadecimal string
	def digest(self,str):
		return hashlib.sha1(str).hexdigest()

	# Encodes a 20-byte SHA1 digest to a list of 20 numerals array according to the algo
	def digest_to_nums(self,d):
		return map(self.hexstr_to_num,self.split_len(self.digest(d),2))

	# Encodes a message to a list of numerals according to the algo
	def msg_to_nums(self,msg):
		return map(self.binstr_to_num,[self.pad_binstr(bin,self.n) for bin in self.split_len(self.str_to_binstr(msg),self.n)])

	# Encodes a message and a stego key according to the algo
	#
	# Returns a list n[]:
	# n[0] is the list of 20 numerals representing "FlagStr1"
	# n[1] is the list of numerals representing the message
	# n[2] is the list of 20 numerals representing "FlagStr2"
	def encode_msg(self,msg,key):
		return [self.digest_to_nums(msg),self.msg_to_nums(msg),self.digest_to_nums(key)]

	# Encodes a derived key according to the algo
	#
	# Returns the list of 20 numerals representing "FlagStr"
	def encode_key(self,key):
		return self.digest_to_nums(key)

	def avg(self,nums):
		n = 0
		for k in nums:
			n += k
		return float(n) / nums.__len__()

	def mean(self,nums,nums_):
		if nums.__len__() < nums_.__len__():
			return 0.
		n = 0
		i = 0
		while i < nums_.__len__():
			n += (nums[i] - nums_[i])
			i += 1
		return float(n) / nums_.__len__()

# Generate chaotic maps
class Chaotic:

	mu = 3.6
	x = 0

	def __init__(self,mu,flagstr):
		self.mu = mu
		self.x = self.gen_chaokey(flagstr)

	# Generates a chaotic key (seed for the chaotic map) according to the algo
	def gen_chaokey(self,flagstr):
		dec = ""
		for i in flagstr:
			dec = dec + str(i)
		return float("0." + dec)

	# Gets the next real number from the chaotic map
	def next(self):
		x_ = self.mu * self.x * (1 - self.x)
		self.x = x_
		return self.x

# Perform the stego algorithm
class PDF_stego:

	# The number of bit to use
	nbits = 4
	
	# Debug logging flag
	debug = False

	# Improvements flag
	improve = False

	# Redundancy parameter, should be in ]0,1[
	redundancy = 0.1

	# Chaotic map parameters, should be in ]3.57,4[
	mu_one = 3.7
	mu_two = 3.8

	# Counter for TJ operators
	tj_count = 0

	def __init__(self,input,debug,improve,red,nbits):
		self.file_op = PDF_file(input)
		self.improve = improve
		self.debug = debug
		self.redundancy = red
		self.nbits = nbits

	def get_tjs(self,line):
		tjs = []
		k = 0
		while k < line.__len__():
			# Parse TJ string from current position
			m = re.search(r'[>)](\-?[0-9]+)[<(]',line[k:])
			if m == None:
				# No more TJ ops
				k = line.__len__()
			else:
				val = int(m.group(1))
				if abs(val) < 2**self.nbits + 1 and val != 0:
					tjs += [abs(val)]
				k += m.end(1)
		return tjs

	def get_tjs_signed(self,line):
		tjs = []
		k = 0
		while k < line.__len__():
			# Parse TJ string from current position
			m = re.search(r'[>)](\-?[0-9]+)[<(]',line[k:])
			if m == None:
				# No more TJ ops
				k = line.__len__()
			else:
				val = int(m.group(1))
				if abs(val) < 2**self.nbits + 1 and val != 0:
					tjs += [val]
				k += m.end(1)
		return tjs

	# Embeds data in a TJ operator
	#
	# val: the original value of the TJ operator
	# ch_one: the next number from chaotic map 1
	# ch_two: the next number from chaotic map 2
	# num: the next numeral to embed, or None if the IND was taken to finish
	#
	# Returns a list res[]
	# If res[0] == True then num was embedded, move on to next numeral
	# If res[0] == False then try to embed num again in the nex operator
	# res[1] is the new operator value (regardless of res[0])
	def embed_op(self,val,ch_one,ch_two,num,start,jitter):
		if abs(val) > 2**self.nbits or val == 0:
			# Do not use TJ op
			return [False,val]
		self.tj_count += 1
		if self.improve and self.tj_count == 1:
			# Embed jitter value
			if jitter < 0:
				self.print_debug('Embedded jitter',jitter - 1)
				return [False, jitter - 1]
			self.print_debug('Embedded jitter',jitter + 1)
			return [False, jitter + 1]
		if ch_two < self.redundancy or num == None or self.tj_count <= start:
			# Use TJ op for a random value
			if val < 0:
				return [False,-(int((2**self.nbits - 1) * ch_one) + 1 )]
			return [False,int((2**self.nbits - 1) * ch_one) + 1]
		# Use TJ op for data
		if val < 0:
			return [True, -num - 1]
		return [True, num + 1]

	# Embeds data in TJ operators from a TJ string
	#
	# line: the TJ string to parse
	# ch_one: chaotic map 1
	# ch_two: chaotic map 2
	# ind: the IND to embed
	# i: the current IND index
	#
	# Returns a list res[]
	# res[0] is the modified line
	# res[1] is the new value of the IND index
	def embed_line(self,line,ch_one,ch_two,ind,i,start,jitter):
		newline = line
		i_ = i
		k = 0
		while k < newline.__len__():
			# Parse TJ string from current position
			m = re.search(r'[>)](\-?[0-9]+)[<(]',newline[k:])
			if m == None:
				# No more TJ ops
				k = newline.__len__()
			else:
				tj = int(m.group(1))
				if i_ < ind.__len__():
					# Try to embed numeral
					op = self.embed_op(tj,ch_one.next(),ch_two.next(),ind[i_],start,jitter)
				else:
					# No more numerals to embed
					op = self.embed_op(tj,ch_one.next(),ch_two.next(),None,start,jitter)
				if op[0]:
					# One numeral was embedded, update IND index
					i_ += 1
				# Insert new value
				newline = newline[:k + m.start(1)] + str(op[1]) + newline[k + m.end(1):]
				# Update current position
				k += m.start(1) + str(op[1]).__len__()
		return [newline,i_]

	# Embeds data with passkey in a PDF file "<file>", outputs stego PDF file "<file>.out.fix.pdf"
	#
	# Returns the number of embedded numerals constituting the data
	def embed(self,data,passkey):
		self.tj_count = 0
		self.print_info("Key","\"" + passkey + "\"")
		self.print_info("Input file","\"" + self.file_op.file_name + ".qdf\"")
		self.print_info("Embedding data, please wait...","")
		self.file_op.uncompress()
		cover_file = open(self.file_op.file_name + ".qdf")
		new_file = ""
		n = Numerals(self.nbits)
		# Get the numerals to embed from the key and the message
		nums = n.encode_msg(data,passkey)
		ind = nums[0] + nums[1] + nums[2]
		tjs = []
		if self.improve:
			# Parse file
			for line in cover_file:
				# Parse line for TJ blocks
				m = re.search(r'\[(.*)\][ ]?TJ',line)
				if m != None:
					tjs += self.get_tjs(m.group(1))
			# Jitter data
			jitter = int(n.mean(tjs,ind))
			ind = map(lambda x: (x + jitter) % (2**self.nbits),ind)
		else:
			jitter = 0
		self.print_debug('FlagStr1 (CheckStr)',nums[0])
		self.print_debug('FlagStr2',nums[2])
		self.print_debug('Data',n.msg_to_nums(data))
		self.print_debug('Jitter',jitter)
		# Initiate chaotic maps
		ch_one = Chaotic(self.mu_one,nums[2])
		ch_two = Chaotic(self.mu_two,nums[2])
		# Parse file
		if self.improve:
			start = int((tjs.__len__() - ind.__len__()) * ch_one.next())
			self.print_debug("Random start position",start)
		else:
			start = 0
		i = 0
		cover_file.seek(0,0)
		for line in cover_file:
			# Parse line for TJ blocks
			m = re.search(r'\[(.*)\][ ]?TJ',line)
			if m == None:
				# No TJ blocks
				new_file += line
			else:
				# Try to embed data in TJ block
				newline = self.embed_line(m.group(1),ch_one,ch_two,ind,i,start,jitter)
				# Insert new block
				new_file += line[:m.start(1)] + newline[0] + line[m.end(1):]
				i = newline[1]
		tjss_ = []
		if self.debug:
			cover_file.seek(0,0)
			tjss = []
			# Parse file
			for line in cover_file:
				# Parse line for TJ blocks
				m = re.search(r'\[(.*)\][ ]?TJ',line)
				if m != None:
					tjs += self.get_tjs(m.group(1))
					tjss += self.get_tjs_signed(m.group(1))
			tjss_ = tjss
			if self.improve:
				self.print_debug('TJ values before',tjss)
				self.print_debug("TJ average before",n.avg(tjss))
				self.print_debug("TJ unsigned average before",n.avg(tjs))
		cover_file.close()
		if i < ind.__len__():
			print "\nError: not enough space available (only " + str(self.tj_count) + ", " + str(ind.__len__()) + " needed).\n"
			return 0
		else:
			self.print_info("Done embedding.","")
			output_file = open(self.file_op.file_name + ".out","w")
			output_file.write(new_file)
			output_file.close()
			output = PDF_file(self.file_op.file_name + ".out")
			output.fix()
			output_fixed = PDF_file(self.file_op.file_name + ".out.fix")
			output_fixed.compress()
			self.print_info("Output file","\"" + self.file_op.file_name + ".out.fix.pdf\"")
			self.print_debug("Embedded data","\"" + data + "\"")
			self.print_debug("Total nb of TJ ops",self.tj_count)
			self.print_debug("Total nb of TJ ops used",ind.__len__())
			self.print_debug("Total nb of TJ ops used for data",nums[1].__len__())
			if self.debug:
				embd_file = open(self.file_op.file_name + ".out.fix")
				embd_file.seek(0,0)
				tjss = []
				# Parse file
				for line in embd_file:
					# Parse line for TJ blocks
					m = re.search(r'\[(.*)\][ ]?TJ',line)
					if m != None:
						tjs += self.get_tjs(m.group(1))
						tjss += self.get_tjs_signed(m.group(1))
				embd_file.close()
				if self.improve:
					self.print_debug('TJ values after',tjss)
					self.print_debug('TJ average after',n.avg(tjss))
					self.print_debug('TJ unsigned average after',n.avg(tjs))
				i = 0
				if self.improve:
					i = 1
				sbugs = []
				while i < tjss.__len__():
					if tjss[i] * tjss_[i] < 0:
						sbugs += ["\t[" + str(i) + "]\t" + str(tjss_[i]) + "\t" + str(tjss[i])]
					i += 1
				if sbugs.__len__() > 0:
					self.print_debug("Sign bugs",sbugs)
			return nums[1].__len__()

	def extract_op(self,val,ch_two):
		if abs(val) > 2**self.nbits or val == 0 or ch_two < self.redundancy:
			# Do not use TJ op
			return 0
		self.tj_count += 1
		if self.tj_count == 1:
			return val
		# Extract data from TJ op
		return abs(val)

	def extract_line(self,line,ch_two):
		k = 0
		tjs = []
		while k < line.__len__():
			# Parse TJ string from current position
			m = re.search(r'[>)](\-?[0-9]+)[<(]',line[k:])
			if m == None:
				# No more TJ ops
				k = line.__len__()
			else:
				# Try to extract numeral
				tj = self.extract_op(int(m.group(1)),ch_two.next())
				if tj != 0:
					# Get value
					tjs += [tj]
				# Update current position
				k += m.end(1)
		return tjs

	# Extracts data of known length from PDF file "<file>" using derived_key, outputs extracted data to "<file>.embd"
	def extract(self,derived_key,length):
		self.tj_count = 0
		self.print_info("Key","\"" + derived_key + "\"")
		self.print_info("Input file","\"" + self.file_op.file_name + "\"")
		self.print_info("Extracting data, please wait...","")
		length_ = length
		# Only works for valid PDF files
		self.file_op.uncompress()
		embedding_file = open(self.file_op.file_name + '.qdf')
		n = Numerals(self.nbits)
		# Get the numerals from the key
		nums = n.encode_key(derived_key)
		self.print_debug('FlagStr',nums)
		# Initiate chaotic map
		ch_two = Chaotic(self.mu_two,nums)
		tjs = []
		# Parse file
		for line in embedding_file:
			# Parse line for TJ blocks
			m = re.search(r'\[(.*)\][ ]?TJ',line)
			if m != None:
				# Try to extract data from TJ block
				tjs += self.extract_line(line,ch_two)
		embedding_file.close()
		if self.improve and tjs.__len__() < 40 + length:
			print "\nError: not enough valid data to retrieve message: " + str(40 + length) + " > " + str(tjs.__len__()) + "\n"
			return -1
		else:
			if self.improve:
				# Extract jitter
				if tjs[0] < 0:
					jitter = tjs[0] + 1
				else:
					jitter = tjs[0] - 1
				self.print_debug("Jitter found",jitter)
			else:
				jitter = 0
			# Jitter data
			tjs = map(lambda x: (x - jitter - 1) % (2**self.nbits), tjs)
			# Extract data
			k = 20
			while k + 20 < tjs.__len__():
				# Look for end position
				if nums == tjs[k:k+20]:
					self.print_debug('End position found',k + 20 - 1)
					if self.improve:
						# Go back to start position according to length, and extract
						start = k-length-20
						self.print_debug('Start position found',start)
					else:
						start = 0
						length_ = k - 20
					checkstr = tjs[start:start + 20]
					embedded = tjs[start + 20:k]
					k = tjs.__len__()
				k += 1
			if k != tjs.__len__() + 1:
				print "\nError: ending code FlagStr not found\n"
				return -1
			else:
				# Decode embedded data
				k = 0
				bin_str = ""
				while k < embedded.__len__():
					bin = n.num_to_binstr(embedded[k],self.nbits)
					if k == embedded.__len__() - 1:
						missing = -(bin_str.__len__() % 8) % 8
						if missing > self.nbits:
							print "\nError: ...\n" #TODO: message
							self.print_debug("Raw data (corrupted)",embedded)
							return -1
						bin_str += bin[bin.__len__() - missing:]
					else:
						bin_str += bin
					k += 1
				emb_chars = map(n.binstr_to_ch,n.split_len(bin_str,8))
				emb_str = ""
				for ch in emb_chars:
					emb_str += ch
				if self.debug:
					self.print_debug('Data Checksum',n.encode_key(emb_str))
					self.print_debug('CheckStr',checkstr)
					self.print_debug('Data',embedded)
				# Check integrity
				if n.digest_to_nums(emb_str) != checkstr:
					print "\nError: CheckStr does not match embedded data\n"
					self.print_debug("Raw data (corrupted)",emb_str)
					return -1
				else:
					self.print_info("Done Extracting.","")
					output_file = open(self.file_op.file_name + ".embd","w")
					output_file.write(emb_str)
					output_file.close()
					self.print_info("Output file","\"" + self.file_op.file_name + ".embd\"")
					self.print_debug("Extracted data","\"" + emb_str + "\"")
					self.print_debug("Total nb of TJ ops",self.tj_count)
					self.print_debug("Total nb of TJ ops used",embedded.__len__() + 40)
					self.print_debug("Total nb of TJ ops used for data",embedded.__len__())
					return 0

	def print_debug(self,name,value):
		if self.debug:
			print '===== ' + name + ' ====='
			print '\t' + str(value)

	def print_info(self,name,value):
		print '+++++ ' + name + ' +++++'
		print '\t' + str(value)

#
#
#
# SCRIPT
#

def main():
	parser = optparse.OptionParser(usage="%prog {embed|extract} [options]", version="%prog 0.0b")
	group0 = optparse.OptionGroup(parser, 'General options')
	group1 = optparse.OptionGroup(parser, 'Basic options for improvements')
	group2 = optparse.OptionGroup(parser, 'Advanced options')
	group0.add_option("-f", "--file", dest="filename",
					  help="use PDF file (may be compressed) FILENAME as input", metavar="FILENAME")
	group0.add_option("-k", "--key", dest="key",
					  help="use KEY as the stego-key", metavar="KEY")
	group0.add_option("-m", "--message", dest="msg",
					  help="use MESSAGE as the data to embed (ignored if extracting)", metavar="MESSAGE")
	group1.add_option("-i", "--improve", action="store_true", dest="improve", default=False,
					  help="use algo improvements [%default]")
	group1.add_option("-l", "--message-length", dest="l", action="store", type="int", default=0,
					  help="use LENGTH as the length of the data to extract (ignored if embedding or if using original algo)", metavar="LENGTH")
	group2.add_option("-d", "--debug", action="store_true", dest="debug", default=False,
					  help="print debug messages [%default]")
	group2.add_option("-n", "--nbits", dest="nbits", action="store", type="int", default=4,
					  help="use NBITS as the number of bits to use for numerals [%default]", metavar="NBITS")
	group2.add_option("-r", "--redundancy", dest="red", action="store", type="float", default=0.1,
					  help="use RED as the redundancy parameter (strictly between 0 and 1) [%default]", metavar="RED")
	parser.add_option_group(group0)
	parser.add_option_group(group1)
	parser.add_option_group(group2)
	(options, args) = parser.parse_args()
	if args.__len__() != 1:
		parser.error("Please use command \"embed\" only or command \"extract\" only.")
	if args[0] == "embed":
		if select.select([sys.stdin,],[],[],0.0)[0]:
			input = ""
			for line in sys.stdin:
				if input.__len__() > 0:
					input += "\n"
				input += line
			sys.stdin = open("/dev/tty")
			options.msg = input
		if options.msg == None:
			options.msg = raw_input("Please enter the message to embed:\n")
		if options.filename == None:
			options.filename = raw_input("Please enter input file name: [\"test.pdf\"]\n")
		if options.filename.__len__() == 0:
			if options.debug:
				print "No file name provided, using default: \"test.pdf\""
			options.filename = "test.pdf"
		if options.key == None:
			options.key = raw_input("Please enter stego-key:\n")
		if options.red == None:
			options.red = "0.1"
		ps = PDF_stego(options.filename,options.debug,options.improve,options.red,options.nbits)
		exit(ps.embed(options.msg,options.key))
	elif args[0] == "extract":
		if options.filename == None:
			options.filename = raw_input("Please enter input file name: [\"test.pdf.out.fix.pdf\"]\n")
		if options.filename.__len__() == 0:
			if options.debug:
				print "No file name provided, using default: \"test.pdf.out.fix.pdf\""
			options.filename = "test.pdf.out.fix.pdf"
		if options.key == None:
			options.key = raw_input("Please enter derived-key:\n")
		if options.l == None:
			options.l = int(raw_input("Please enter data length:\n"))
		ps = PDF_stego(options.filename,options.debug,options.improve,options.red,options.nbits)
		exit(ps.extract(options.key,options.l))
	else:
		parser.error("Please use command \"embed\" only or command \"extract\" only.")

if __name__ == '__main__':
    main()

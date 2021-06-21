
# NOTICE: using NO external libraries! Only std libs that come with python

import sys
import os.path
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from html.entities import name2codepoint
import urllib.request
import urllib.parse
import logging 
import datetime

g_converter_config = {}

# where to save converted markdown posts
g_converter_config["md_file_save_path"] = "converted_posts" 

# where to save downloaded images
g_converter_config["image_save_path"] = "fetched_images"

# path prefix to use in markdown to access downloaded images
g_converter_config["img_path_relative_to_md"] = "../fetched_images"

# html to markdown conversion settings
g_converter_config["images_on_own_line"] = True
g_converter_config["allow consecutive empty lines"] = False
g_converter_config["ignore empty head tags"] = True
g_converter_config["ignore downloaded image cache"] = False

# settings to ease debugging
# g_converter_config["dont download use demo image"] = "../demo.jpg"
g_converter_config["stop after one conversion"] = False

HAPPY_LOG = 25
class CustomFormatter(logging.Formatter):
    """Logging Formatter to add colors and count warning / errors"""

    grey = "\x1b[38;21m"
    yellow = "\x1b[33;21m"
    red = "\x1b[31;21m"
    bold_red = "\x1b[31;1m"
    reset = "\x1b[0m"
    green = "\x1b[1;32m"
    format_err = "%(asctime)s:%(levelname)s:%(name)s: %(message)s (%(filename)s:%(lineno)d)"
    format_info = "%(asctime)s:%(levelname)s:%(name)s: %(message)s"
    format_happy = "%(asctime)s:HAPPY:%(name)s: %(message)s"

    FORMATS = {
        logging.DEBUG: grey + format_info + reset,
        logging.INFO: grey + format_info + reset,
        HAPPY_LOG: green + format_happy + reset,
        logging.WARNING: yellow + format_err + reset,
        logging.ERROR: red + format_err + reset,
        logging.CRITICAL: bold_red + format_err + reset,
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt='%I:%M:%S')
        return formatter.format(record)

formatter = CustomFormatter()
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)


html_logger = logging.getLogger('html parser')
html_logger.setLevel(logging.DEBUG)
html_logger.addHandler(ch)

converter_logger = logging.getLogger('converter')
converter_logger.setLevel(logging.DEBUG)
converter_logger.addHandler(ch)

class HTMLToMarkdownParser(HTMLParser):
	def __init__(self):
		HTMLParser.__init__(self)
		self.md = ""
		# stacks to keep track of embedded elements
		self.links = [] 
		self.list = [] # saves either last list number or unordered
		self.spans = [] # tracks spans
		self.escape_md_data = True # used to temporarily disable escaping (for code)

		self.nested_table_states = [] # each state is one of 'filled-th_%d' 'filling_body' 'ignoring'

		# single-table support:
		# self.table_state = "waiting" # waiting / new / filling
		# self.table_columns = 0

		self.last_image_fname = ""

	def ensure_on_newline(self):
		"""
			solves issues that html has block fomating on certain attributes and md doesn't.
			ie, in html can have inline link then h1: some text <a href="...">read more</a> <h1>hi</h1>
			html knows to handle that.
			but in markdown, h1 needs to be on a new line - though in conversion can't just 
			end every </a> tag with a newline because sometimes want to save display of inline text.

			this function addresses that issue by making sure h1 and friends are started on a newline
		"""
		if (len(self.md) > 0) and (self.md[-1] != "\n"):
			self.md += "\n"
			html_logger.debug("adding newline")
		else:
			html_logger.debug("not adding new line")

	def handle_starttag(self, tag, attrs):
		html_logger.debug(f"Start tag: {tag}")	
		for attr in attrs:
			html_logger.debug(f"     attr:{attr}")
		
		attr_dict = dict(attrs)
		if tag == "p":
			# only drop line if not in table
			if not self.nested_table_states or self.nested_table_states[-1] == "ignoring":
				self.md += "\n"
		elif tag == "i":
			self.md += "*"
		elif tag == "blockquote":
			self.md += "> "	
		elif tag == "b":
			self.md += "**"
		elif tag == "strike":
			self.md += "~~"
		elif tag == "hr":
			self.ensure_on_newline() 
			self.md += "***"
			self.ensure_on_newline() 			
		elif tag in ["u", "sup", "sub", "iframe", "script", "style"]: # passthrough
			self.md += f"<{tag}>"
		elif tag == "a":
			if ("href" in attr_dict) and (attr_dict["href"] != "https://www.blogger.com/null"):
				self.md += "["
				self.links.append(attr_dict["href"])
			else:
				self.links.append("unsupported_anchor")
		elif tag == "img":
			if g_converter_config["images_on_own_line"]:
				self.ensure_on_newline()
			self.last_image_fname = urllib.parse.urlsplit(attr_dict["src"]).path.split("/")[-1]
			published_img_path = download_img_src(attr_dict["src"])
			if "alt" in attr_dict:
				alt_text = attr_dict["alt"]
			else:
				alt_text = ""
			self.md += f"![{alt_text}]({published_img_path})"
		elif tag in ["div", "html", "body"]:
			pass # do nothing
		elif tag == "h1":
			self.ensure_on_newline()
			self.md += "# "
		elif tag == "h2":
			self.ensure_on_newline()
			self.md += "## "
		elif tag == "h3":
			self.ensure_on_newline()
			self.md += "### "
		elif tag == "h4":
			self.ensure_on_newline()
			self.md += "#### "
		elif tag == "h5":
			self.ensure_on_newline()
			self.md += "##### "			
		elif tag == "ol":
			self.links.append(0)
		elif tag == "ul":
			self.links.append("unordered")
		elif tag == "li":
			self.ensure_on_newline()
			if self.links[-1] == "unordered":
				self.md += "* " 
			else:
				self.links[-1] += 1
				self.md += str(self.links[-1]) + ". "
		elif tag == "span":
			"""
				taking care of setting font type as 'Courier' in Blogger.
				Usually this was to identify a techincal word/function.
				The md alternative is using backticks. Ie:
				
				<span style="font-family: courier;">malloc(0x10)</span>
				will be converted to
				`malloc(0x10)`

			"""
			if "style" in attr_dict.keys() and attr_dict["style"] == "font-family: courier;":
				self.md += "`"
				self.spans.append("backtick_span")
				self.escape_md_data = False
			else:
				self.spans.append("ignored_span")
		elif tag == "code":
			self.ensure_on_newline()
			self.md += "```\n"
			self.escape_md_data = False
		elif tag == "br":
			if g_converter_config["allow consecutive empty lines"]:
				self.md += "\n"
			else:
				self.ensure_on_newline()

		elif tag == "table":
			if "class" in attr_dict and "tr-caption-container" in attr_dict["class"]:
				# this is a table to align the image caption. ignore it
				self.nested_table_states.append("ignoring")
				html_logger.debug("found caption table. ignoring")
			else:
				self.nested_table_states.append("filled-th_0")
		elif tag == "tbody":
			pass # don't care
		elif tag == "tr":
			if self.nested_table_states and self.nested_table_states[-1] != "ignoring":
				self.ensure_on_newline()
				self.md += "| "
		elif tag == "td" or tag == "th":
			pass
		else:
			html_logger.warning(f"doing nothing for {tag}")

	def handle_endtag(self, tag):
		html_logger.debug(f"End tag  {tag}")

		if tag == "p":
			# only drop line if not in table
			if not self.nested_table_states or self.nested_table_states[-1] == "ignoring":
				self.md += "\n"
				# might have had something like </code> that already dropped us a line
				self.ensure_on_newline() 
		elif tag == "i":
			self.md += "*"
		elif tag == "blockquote":
			self.md += "\n"			
		elif tag == "b":
			self.md += "**"
		elif tag == "strike":
			self.md += "~~"
		elif tag in ["u", "sup", "sub", "iframe", "script", "style"]: # passthrough
			self.md += f"</{tag}>"
		elif tag == "a":
			last_link = self.links.pop()
			"""
			algo: each time save name of last image. 
			if pointing at blogspot AND href is urlencode(last_image), means we're point to that image -> don't want to include the link
			"""
			if "blogspot.com" in last_link and last_link.endswith('/' + self.last_image_fname):
				# dont want to include this link
				# must remove previous '[' already placed
				try:
					"""
					current sitation:
					self.md = 
					...
					[\n\n
					![some alt text](/assets/img/posts\trimmed+with+subtitles.gif)WE_ARE_HERE

					need to remove first '[' in the example above
					"""
					if self.md[-1] != ")":
						raise KeyError(f"expected ')' have '{self.md[-1]}'")
					# find start of alt text
					idx_alt_text_start = self.md.rfind('![')
					open_bracket_to_delete_idx = self.md[:idx_alt_text_start].rfind("[")
					self.md = self.md[:open_bracket_to_delete_idx] + self.md[open_bracket_to_delete_idx+1:]

				except Exception as e:
					html_logger.warning(f"tried removing all traces of blogger image link, but got exception: {e}")
					raise
			elif last_link != "unsupported_anchor":
				self.md += f"]({last_link})"
			else:
				pass # do nothing
		elif tag in ["div", "html", "body"]:
			pass # do nothing
		elif tag == "img":
			pass # do nothing
		elif tag in ["h1", "h2", "h3", "h4", "h5"]:
			if g_converter_config["ignore empty head tags"]:
				last_line = self.md[self.md.rfind("\n"):]
				if last_line.replace("#", "").replace(" ", "") != "":
					# has text
					self.md += "\n"
			else:
				self.md += "\n"
		elif tag in ["ol", "ul"]:
			self.links.pop()
			self.md += "\n"
		elif tag == "li":
			self.md += "\n"	
		elif tag == "span":
			last_span = self.spans.pop()
			if last_span == "backtick_span":
				self.escape_md_data = True
				self.md += "`"
			else:
				pass # ignoring this span
		elif tag == "code":
			self.ensure_on_newline()
			self.md += "```\n"
			self.escape_md_data = True
		elif tag == "br":
			pass				

		elif tag == "table":
			if self.nested_table_states == [] or (self.nested_table_states[-1] != "filling_body" and self.nested_table_states[-1] != "ignoring"):
				html_logger.warn(f"reached </table> in impossible state: {self.nested_table_states}")
				raise Exception("bug in table parsing.")
			self.nested_table_states.pop()
		elif tag == "tbody":
			pass # don't care
		elif tag == "td" or tag == "th":
			if self.nested_table_states and self.nested_table_states[-1] != "ignoring":
				if self.nested_table_states[-1].startswith("filled-th_"):
					filled_already = int(self.nested_table_states[-1].split("_")[1])
					self.nested_table_states[-1] = "filled-th_" + str(filled_already+1)
				self.md += " |"
		elif tag == "tr":
			if self.nested_table_states and self.nested_table_states[-1] != "ignoring":
				if self.nested_table_states[-1].startswith("filled-th_"):
					filled_already = int(self.nested_table_states[-1].split("_")[1])
					self.md += "\n" + "---".join(["|"]*(filled_already+1))
					self.nested_table_states[-1] = "filling_body"
				else:
					self.ensure_on_newline()
		else:
			html_logger.warning(f"doing nothing after {tag}")

	def handle_data(self, data):
		html_logger.debug(f"Data     :{data} (len: {len(data)})")

		if data.replace("\n", "").replace("\r", "").replace(" ", "").replace("\t", "") == "":
			# only new lines
			html_logger.debug("only whitespaces. skipping")
			return

		if self.escape_md_data:
			self.md += escape_md(data)
		else:
			self.md += data

	def handle_comment(self, data):
		html_logger.debug(f"Comment  :{data}")
		html_logger.info(f"ignoring html comment '{data}'")

	def handle_entityref(self, name):
		c = chr(name2codepoint[name])
		html_logger.debug(f"Named ent:{c}")
		html_logger.warning(f"entity ref handeling unsupported. Ignoring ent: {c}")

	def handle_charref(self, name):
		if name.startswith('x'):
			c = chr(int(name[1:], 16))
		else:
			c = chr(int(name))
		html_logger.debug(f"Num ent  :{c}")
		html_logger.warning(f"char ref handeling unsupported. Ignoring ent: {c}")

	def handle_decl(self, data):
		html_logger.debug(f"Decl     :{data}")
		html_logger.info(f"ignoring decl '{data}'")


def download_img_src(src_url):
	if "dont download use demo image" in g_converter_config:
		return g_converter_config["dont download use demo image"]
	img_name = urllib.parse.unquote(src_url[src_url.rfind("/")+1:])
	converter_logger.debug('img_name:' + img_name)
	save_name = os.path.join(g_converter_config["image_save_path"], img_name)
	converter_logger.debug("saving @" + save_name)

	if g_converter_config["ignore downloaded image cache"] or not os.path.isfile(save_name):
		converter_logger.info(f"downloading '{src_url}'")
		urllib.request.urlretrieve(src_url, save_name)  # using this instead of requests because it's preinstalled
	else:
		converter_logger.info("found image in cache")
	
	return os.path.join(g_converter_config["img_path_relative_to_md"], img_name)


def escape_md(s):
	return s.replace("#", "\\#").replace("_", "\\_").replace("{", "\\{").replace("}", "\\}")\
			.replace("[", "\\[").replace("]", "\\]").replace("-", "\\-").replace("!", "\\!")\
			.replace("(", "\\(").replace(")", "\\)").replace("+", "\\+").replace("*", "\\*")


def convert_html_to_md(html):
	parser = HTMLToMarkdownParser()
	parser.feed(html)
	return parser.md


def convert_post_to_md(post_xml, output_md_formatter=None):
	post_data = {}
	post_data["blogger_id"] = post_xml.find("{http://www.w3.org/2005/Atom}id").text
	post_data["author"] = post_xml.find("{http://www.w3.org/2005/Atom}author").find("{http://www.w3.org/2005/Atom}name").text
	post_data["published"] = datetime.datetime.strptime(post_xml.find("{http://www.w3.org/2005/Atom}published").text,'%Y-%m-%dT%H:%M:%S.%f%z')
	post_data["title"] = post_xml.find("{http://www.w3.org/2005/Atom}title").text
	post_data["categories"] = [c.attrib["term"] for c in post_xml.findall("{http://www.w3.org/2005/Atom}category") \
									if "http://schemas.google.com/blogger/2008/kind#post" != c.attrib["term"]]

	# Ensure have everything. Otherweise can't proceeed because will error later
	for k,v in post_data.items():
		if v == None:
			converter_logger.error(f"skipping post '{post_data['title'] or post_data['blogger_id']}' because don't have post's '{k}' element")
			return

	converter_logger.info(f"converting '{post_data['title']}'")
	post_data["md"] = convert_html_to_md(post_xml.find("{http://www.w3.org/2005/Atom}content").text)

	if output_md_formatter:
		output_md_formatter(post_data)
	else:
		md_file_name = urllib.parse.quote('-'.join(post_data['title'].split(' ')), safe='') + ".md"
		save_path = os.path.join(g_converter_config["md_file_save_path"], md_file_name)
		converter_logger.log(HAPPY_LOG,f"saving '...{md_file_name}'")
		open(save_path, "w", encoding="utf-8").write(post_data["md"])
	

def extract_entry_kind(e):
	cs = e.findall("{http://www.w3.org/2005/Atom}category")
	for c in cs:
		if c.attrib["scheme"] == "http://schemas.google.com/g/2005#kind":
			return c.attrib["term"].split("#")[-1]

	raise KeyError("Couldn't find the entry type (blogger setting/blogger comment/blogger post)")


def ensure_have_folder(f):
	if not os.path.isdir(f):
		converter_logger.info(f"creating folder '{f}'")
		os.makedirs(f)


def convert_posts_to_md(xml_path, output_md_formatter=None):
	ensure_have_folder(g_converter_config["md_file_save_path"])
	ensure_have_folder(g_converter_config["image_save_path"])

	root = ET.parse(xml_path).getroot()
	# root is currently point at the 'feed' elemtn

	xml_gen = root.find('{http://www.w3.org/2005/Atom}generator')
	if xml_gen.text != "Blogger":
		converter_logger.warning(f"Expected 'Blogger' XML generator. Found generator {xml_gen.text}")

	if xml_gen.attrib["version"] != "7.00":
		converter_logger.warning(f"Only tested on Blogger XML generator version 7.00. Found version: {xml_gen.attrib['version']}")

	for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
		if "post" == extract_entry_kind(entry):
			try:
				convert_post_to_md(entry, output_md_formatter)
			except NotImplementedError as e:
				converter_logger.error(f"skipping '{entry.find('{http://www.w3.org/2005/Atom}title').text or entry.find('{http://www.w3.org/2005/Atom}id').text}' because exception '{str(e)}'")
			
			if g_converter_config["stop after one conversion"]:
				converter_logger.info("stopping after one conversion")
				return


def main():
	if len(sys.argv) != 2:
		print("usage: convert_blogger_xml_to_md.py <path to blogger XML>")
		print("please create a backup of your blogger"
			  " posts (https://support.google.com/blogger/answer/41387)"
			  " and provide the path to the generated XML")
		return 1

	convert_posts_to_md(sys.argv[1])
	converter_logger.log(HAPPY_LOG, "")
	converter_logger.log(HAPPY_LOG, "****")
	converter_logger.log(HAPPY_LOG, "Done converting Blogger posts to Markdown.")
	converter_logger.log(HAPPY_LOG, "Take care, polar bear")
	converter_logger.log(HAPPY_LOG, "****")
	return 0


if __name__ == '__main__':
	main()

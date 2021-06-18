
# goal: as little non-default dependencies as possible

# standard libraries on all python installs
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
import logging #todo: add more logging
from html.parser import HTMLParser
from html.entities import name2codepoint

class HTMLToMarkdownParser(HTMLParser):
	def __init__(self):
		HTMLParser.__init__(self)
		self.md = ""
		self.links = [] # need stack to keep track of links

	def ensure_on_newline(self):
		"""
			solves issues that html has block fomating on certain attributes and md doesn't.
			ie, in html can have inline link then h1: some text <a href="...">read more</a> <h1>hi</h1>
			html knows to handle that.
			but in markdown, h1 needs to be on a new line - though can't end every </a> tag with a newline because
			sometimes want to save display of inline text.

			this function addresses that issue by making sure h1 and friends are started on a newline
		"""
		if self.md[-1] != "\n":
			self.md += "\n"

	def handle_starttag(self, tag, attrs):
		print("Start tag:", tag)
		attr_dir = {}
		for attr in attrs:
			print("     attr:", attr)
			attr_dir[attr[0]] = attr[1]

		if tag == "p":
			self.md += "\n"
		elif tag == "i":
			self.md += "*"
		elif tag == "a":
			self.md += "["
			self.links.append(attr_dir["href"])
		elif tag == "img":
			self.md += "\(will add img support later\)"
		elif tag == "div":
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
		else:
			print(f"doing nothing for {tag}")


	def handle_endtag(self, tag):
		print("End tag  :", tag)

		if tag == "p":
			self.md += "\n"			
		elif tag == "i":
			self.md += "*"
		elif tag == "a":
			self.md += "]"
			last_link = self.links.pop()
			self.md += f"({last_link})"
		elif tag == "div":
			pass # do nothing
		elif tag == "img":
			pass # do nothing
		elif tag in ["h1", "h2", "h3"]:
			self.md += "\n"

		else:
			print(f"doing nothing for {tag}")

	def handle_data(self, data):
		print("Data     :", data)

		self.md += escape_md(data)

	def handle_comment(self, data):
		print("Comment  :", data)

	def handle_entityref(self, name):
		c = chr(name2codepoint[name])
		print("Named ent:", c)

	def handle_charref(self, name):
		if name.startswith('x'):
			c = chr(int(name[1:], 16))
		else:
			c = chr(int(name))
		print("Num ent  :", c)

	def handle_decl(self, data):
		print("Decl     :", data)

def escape_md(s):
	return s.replace("#", "\\#").replace("_", "\\_").replace("{", "\\{").replace("}", "\\}")\
			.replace("[", "\\[").replace("]", "\\]").replace("-", "\\-").replace("!", "\\!")\
			.replace("(", "\\(").replace(")", "\\)").replace("+", "\\+")

def convert_html_to_md(html):
	"""
		where the heavy lifting happens
	"""
	print("-"*100)
	
	parser = HTMLToMarkdownParser()
	parser.feed(html)
	print("-"*100)
	open("out.md", "w").write(parser.md)


def convert_post_to_md(post_xml):
	post_data = {}
	post_data["published"] = post_xml.find("{http://www.w3.org/2005/Atom}published").text
	post_data["categories"] = [c.attrib["term"] for c in post_xml.findall("{http://www.w3.org/2005/Atom}category") \
									if "http://schemas.google.com/blogger/2008/kind#post" != c.attrib["term"]] # todo: maybe clean
	post_data["title"] = post_xml.find("{http://www.w3.org/2005/Atom}title").text
	post_data["author"] = post_xml.find("{http://www.w3.org/2005/Atom}author").find("{http://www.w3.org/2005/Atom}name").text

	post_data["md"] = convert_html_to_md(post_xml.find("{http://www.w3.org/2005/Atom}content").text)
	#todo: support extracting comments

	print(f"post_data: {post_data}")

def convert_posts_to_md(xml_path):
	tree = ET.parse(xml_path)
	root = tree.getroot()
	# root is currently point at the 'feed' elemtn

	# minor sanity checks
	xml_gen = root.find('{http://www.w3.org/2005/Atom}generator')
	if xml_gen.text != "Blogger":
		logging.warning(f"Expected 'Blogger' XML generator. Found generator {xml_gen.text}")

	if xml_gen.attrib["version"] != "7.00":
		logging.warning(f"Only tested on Blogger XML generator version 7.00. Found version: {xml_gen.attrib['version']}")

	for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
		if ".post-" in (entry.find("{http://www.w3.org/2005/Atom}id").text):
			convert_post_to_md(entry)
			break # only do one for now :)

		# todo might want to support converting pages too


def main():
	if len(sys.argv) != 2:
		print("usage: convert_blogger_xml_to_md.py <path to blogger XML>")
		print("please create a backup of your blogger"
			  " posts (https://support.google.com/blogger/answer/41387)"
			  " and provide the path to the generated XML")
		return 1

	in_blogger_xml = sys.argv[1]
	out_md = "out.md"

	print(f"in : {in_blogger_xml}")
	print(f"out: {out_md}")

	convert_posts_to_md(in_blogger_xml)

if __name__ == '__main__':
	# for local testing
	sys.argv = ["convert_blogger_xml_to_md.py", "blog-06-17-2021.xml"]
	main()
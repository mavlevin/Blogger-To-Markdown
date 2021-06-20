
from convert_blogger_xml_to_md import convert_html_to_md

def main():
	in_html = open("table_test.html", "r").read()
	out_md = convert_html_to_md(in_html)
	open("out.md", "w").write(out_md)

if __name__ == '__main__':
	main()
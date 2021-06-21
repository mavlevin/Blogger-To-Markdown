import sys
from convert_blogger_xml_to_md import \
	convert_posts_to_md, g_converter_config, converter_logger, HAPPY_LOG
import urllib
import os

def make_post_preamble(post_data):
	preamble = "---\n"
	preamble += "layout: post\n"
	preamble += f"title: >\n    {post_data['title']}\n"
	preamble += "hide_title: false\n"
	# consider putting first pic automatically
	# feature-img: "assets/img/sample.png"
	# thumbnail: "assets/img/thumbnails/sample-th.png"
	preamble += f"tags: {post_data['categories']}\n"
	preamble += "excerpt_separator: <!--more-->\n"
	preamble += "---\n"
	return preamble


def save_md_file_jekyll_style(post_data):

	preamble = make_post_preamble(post_data)
	
	md_file_name = f"{post_data['published'].strftime('%Y-%m-%d')}-{urllib.parse.quote('-'.join(post_data['title'].split(' ')), safe='')}.md"
	save_path = os.path.join(g_converter_config["md_file_save_path"], md_file_name)
	converter_logger.log(HAPPY_LOG,f"saving '...{md_file_name}'")



	open(save_path, "w", encoding="utf-8").write(preamble + post_data["md"])

def main():
	if len(sys.argv) != 2:
		print("usage: convert_blogger_xml_to_jekyll.py <path to blogger XML>")
		print("please backup your blogger"
			  " posts (https://support.google.com/blogger/answer/41387)"
			  " and provide the path to the downloaded backup XML")
		return 1

	# jekyll-specific
	g_converter_config["md_file_save_path"] = "_posts"
	g_converter_config["image_save_path"] = "assets/img/posts" 
	g_converter_config["img_path_relative_to_md"] = "/assets/img/posts"

	convert_posts_to_md(sys.argv[1], save_md_file_jekyll_style)
	converter_logger.log(HAPPY_LOG, "")
	converter_logger.log(HAPPY_LOG, "****")
	converter_logger.log(HAPPY_LOG, "Done converting Blogger posts to Markdown.")
	converter_logger.log(HAPPY_LOG, "Take care, polar bear")
	converter_logger.log(HAPPY_LOG, "****")
	return 0


if __name__ == '__main__':
	main()
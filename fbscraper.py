from __future__ import print_function

import re
import json
from dateutil.parser import parse, tz
import urllib.request

import facepy
from facepy import GraphAPI
import commonregex
# Put Facebook 'Access Token' in a plain text file ACCESS_TOKEN in same dir.
# To get an access token follow this SO answer:
# http://stackoverflow.com/a/16054555/1780891

with open('./FB_ACCESS_TOKEN', 'r') as f:
	access_token = f.readline().rstrip('\n')

graph = GraphAPI(access_token)

def get_picture(post_id, dir="."):
	base_query = post_id + '?fields=object_id'
	try:
		pic_id = graph.get(base_query)['object_id']
	except KeyError:
		return None

	try:
		pic = graph.get('{}?fields=images'.format(pic_id))
		return (pic['images'][0]['source'])
	except facepy.FacebookError:
		return None
	except facepy.exceptions.FacebookError: 
		return None


def get_event_picture(post_id, dir="."):
	base_query = post_id + '?fields=object_id'
	try:
		pic_id = graph.get(base_query)['object_id']
	except KeyError:
		return None
	try:
		pic = graph.get('{}?fields=cover'.format(pic_id))
		return (pic['cover']['source'])
	except facepy.FacebookError:
		return None


def get_link(post_id):
	base_query = post_id + '?fields=link'
	try:
		link = graph.get(base_query)['link']
	except KeyError:
		return None

	return link


def get_event(post_id, page_id):
	base_query = page_id + '/events'
	all_events = graph.get(base_query)

	message = """
{}
Date: {}
Time: {}
Veunu: {}
	"""
	for event in all_events['data']:
		if event['id'] in post_id:
			DateTime = prettify_date([{'created_time': event['start_time']}])
			if 'description' in event.keys():  # checking if the event have description
				message = message.format(event['description'],
										 DateTime[0]['real_time'],
										 DateTime[0]['real_date'],
										 event['place']['name'])
			else:
				message = message.format(event['name'],
										 DateTime[0]['real_time'],
										 DateTime[0]['real_date'],
										 event['place']['name'])
			return message


def get_shared_post(post_id):
	base_query = post_id + '?fields=parent_id'
	# getting if of the original post
	parent_id = graph.get(base_query)['parent_id']
	query = parent_id + '?fields=message'
	original_message = graph.get(query)['message']
	return original_message


def get_feed(page_id, pages=1):
	# check last update time
	try:
		old_data = json.load(open('{}.json'.format(page_id), 'r'))
		last_post_time = parse(old_data[0]['created_time'])
	except FileNotFoundError:
		old_data = []
		last_post_time = parse("1950-01-01T12:05:06+0000")

	base_query = page_id + '/feed?limit=2'
	# scrape the first page
	feed = graph.get(base_query)
	new_page_data = feed['data']

	data = []
	is_new_post = (parse(new_page_data[0]['created_time']) > last_post_time)

	if is_new_post:
		data = new_page_data

	# determine the next page
	next_page = feed['paging']['next']
	next_search = re.search('.*(\&until=[0-9]+)', next_page, re.IGNORECASE)
	if next_search:
		the_until_arg = next_search.group(1)

	pages = pages - 1

	# scrape the rest of the pages
	while (next_page is not False) and is_new_post and pages > 0:
		the_query = base_query + the_until_arg
		# logger.addLog('baking:{}'.format(the_query),"Facebook")
		try:
			feed = graph.get(the_query)
			new_page_data = feed['data']
			is_new_post = (
				parse(new_page_data[0]['created_time']) > last_post_time)

			data.extend(new_page_data)
		except facepy.exceptions.OAuthError:
			break

		# determine the next page, until there isn't one
		try:
			next_page = feed['paging']['next']
			next_search = re.search(
				'.*(\&until=[0-9]+)', next_page, re.IGNORECASE)
			if next_search:
				the_until_arg = next_search.group(1)
		except IndexError:
			next_page = False
		pages = pages - 1
		for post_dict in data:
			post_dict['pic'] = get_picture(post_dict['id'], dir='docs')
			post_dict['link'] = get_link(post_dict['id'])
			try :  #Events and shared post have story key
				if "event" in post_dict['story'] :
					post_dict['message'] = get_event(post_dict['id'], page_id)
					post_dict['pic'] = get_event_picture(post_dict['id'],dir='docs')
				elif "shared" in post_dict['story'] :
					post_dict['message'] = '<b>' + post_dict['story'] + '</b>' + '\n\n' + get_shared_post(post_dict['id']) 
			except KeyError :
				pass


	data.extend(old_data)
	data.sort(key=lambda x: parse(x['created_time']), reverse=True)
	return data


def remove_duplicates(data):
	uniq_data = []
	for item in data:
		if item not in uniq_data:
			uniq_data.append(item)

	return uniq_data


def prettify_date(data):
	for item in data:
		date = parse(item['created_time'])
		tzlocal = tz.gettz('Asia/Kolkata')
		local_date = date.astimezone(tzlocal)
		item['real_date'] = local_date.strftime('%d-%m-%Y')
		item['real_time'] = local_date.strftime('%I:%M%p')
	return data


def get_aggregated_feed(_id):
	"""
	Aggregates feeds give a list of pages and their ids.

	Input: A list of tuples
	Output: Combined list of posts sorted by timestamp
	"""
	page_data = get_feed(_id)
	for data_dict in page_data:
		data_dict['source'] = _id
   # data.extend(page_data)
	page_data.sort(key=lambda x: parse(x['created_time']), reverse=True)
	page_data = prettify_date(page_data)
	parser = commonregex.CommonRegex()
	for post in page_data:
		if 'message' not in post:
			post['message'] = "" #adding dummy message so if a post have no text in it send message will not give error
	page_data = remove_duplicates(page_data)    
	page_data.sort(key=lambda x: parse(x['created_time']), reverse=True)
	#
	json.dump(page_data, open('{}.json'.format(_id), 'w'))
	return page_data[0]['id']

def enable_links(message,parser):
	
	links = parser.links(message)
	links = list(set(links))
	url_identifier = ["www","http","bit.ly",".com",".co.in"]
	for link in links:
		flag = 0
		for keyword in url_identifier :
			if keyword in link :
				flag = 1
				break
		if flag is 0 :
			break
		http_link = link
		if not link.startswith('http'):
			http_link = "http://{}".format(link)
		if len(link) < 25:
			link = link[0:25]
			message = message.replace(link, "<{}>|{}".format(http_link, link) , 1)
		else:    
			message = message.replace(link, "<{}>|{}".format(http_link, link[0:25]+"...") ,1 ) 
	return message
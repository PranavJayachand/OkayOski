# encoding: utf-8
from bs4 import BeautifulSoup
import requests
import time
import unicodedata
import copy
from datetime import date
from datetime import timedelta

class Mode(): #enum
	MENU = 1
	SCHEDULE = 2

class Cal_Dining_Webscraper():
	menu_to_schedule = {u' Cafe_3': u'Café 3', u' Clark_Kerr_Campus': u'Clark Kerr', u' Crossroads': u'Crossroads', u' Foothill': u'Foothill'}
	schedule_to_menu = dict([(value, key) for key, value in menu_to_schedule.items()])
	def __init__(self, mode):
		if mode == 'MENU':
			self.mode = Mode.MENU
			self.url = 'https://caldining.berkeley.edu/menu.php'
		else: # mode == 'SCHEDULE'
			self.mode = Mode.SCHEDULE
			self.url = 'https://caldining.berkeley.edu/locations/hours-operation/week-of-{}'.format(self.get_sundays_date())
		self.loc = Cal_Dining_Webscraper.menu_to_schedule[u' Crossroads']
		self.response = requests.get(self.url)
		self.soup = BeautifulSoup(self.response.text, "html.parser")

	def change_mode(self, new_mode='MENU', loc_text=u'Crossroads'):
		if new_mode == 'MENU':
			self.mode = Mode.MENU
			self.url = 'https://caldining.berkeley.edu/menu.php'
		else: # mode == 'SCHEDULE'
			self.mode = Mode.SCHEDULE
			self.url = 'https://caldining.berkeley.edu/locations/hours-operation/week-of-{}'.format(self.get_sundays_date())
		self.loc = loc_text
		return self

	def update(self):
		self.response = requests.get(self.url)
		self.soup = BeautifulSoup(self.response.text, "html.parser")

	def get_text(self): #returns a string list of all entries LISTLISTLIST
		try:
			self.update()
			result = []
			if self.mode == Mode.MENU:
				menu_loc = self.soup.find('div', 'menu_wrap_overall')
				while menu_loc:
					# menu_list = self.soup.findAll('div', 'desc_wrap_ck3')
					curr_menu = menu_loc.find('div', 'desc_wrap_ck3')
					while curr_menu:
						for loc_time in curr_menu.findAll('h3'):
							if loc_time.get_text() == Cal_Dining_Webscraper.schedule_to_menu[self.loc]:
								result += [str(loc_time.get_text().strip() + '\n')]
								for entries in curr_menu.findAll('p'):
									result += [str(entries.getText())]
						curr_menu = curr_menu.find_next_sibling('div', 'desc_wrap_ck3')
					menu_loc = menu_loc.find_next_sibling('div', 'menu_wrap_overall')
			else:
				dateobj = date.today()
				today = dateobj.strftime("%A")
				time_table = self.soup.find('p', 'title2', text=self.loc).find_next_sibling('table')
				rows = time_table.find_all('tr')
				day_index = 4
				list_of_days = rows[0].find_all('th')
				for i in range(len(list_of_days)):
					if list_of_days[i].text == today:
						day_index = i
						break
				for row in rows[1:]:
					if row:
						row_element_list = row.find_all('td')
						result.append(str(row_element_list[0].text.strip()) + ' - ' + str(row_element_list[day_index].text.strip()))
		except:
			result = ["N/A"]
		return result

	def get_sundays_date(self):
		today = date.today()
		day_num = today.weekday()
		to_sunday = timedelta(days= 6 - day_num)
		sunday = today + to_sunday
		return sunday.strftime('%b%d').lower().replace('0','')

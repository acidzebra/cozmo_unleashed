#!/usr/bin/env python3
#
# WHAT THIS PROGRAM DOES
#
# SHORT VERSION: this program makes Cozmo play until he runs low on battery, then makes him find and dock with his charger. 
# Once his battery is fully recharged, he will leave the dock and start playing again. Rinse, repeat.
#
# You can run this program as-is but it is likely some things will need to be tweaked to suit your Cozmo and environment.
#
# AUTOMATIC DOCK FINDING AND DOCKING
# this is highly reliant on a number of factors, including having enough ambient light, how big the area Cozmo has to explore is,
# and just sheer blind luck sometimes. The built-in camera of Cozmo is not very high rez, and the dock icon is a little small.
# 
#
# The surface Cozmo moves on can be more slippery or less than my environment, this will impact things like docking.
# On my table's surface, I do two 95 degree turns, this makes it so Cozmo has a high rate of successful dockings.
# Look for these two lines in the code and adjust as necessary
# robot.turn_in_place(degrees(95)).wait_for_completed()
# robot.turn_in_place(degrees(95)).wait_for_completed()
#
# Your Cozmo's battery will have slightly different upper and lower limits.
# there is a lower threshold at which Cozmo will switch states and start looking for his charger.
# The variable is called lowbatvoltage, 3.7 is the setting that works for me. 
# a higher value will cause Cozmo to start looking for his dock sooner.
#
# have a look at the section called
# CONFIGURABLE VARIABLES
# for more stuff
#
# DETAILED VERSION:
# This program defines a number of 'states' for Cozmo:
# State 1: on charger, charging
# State 2: on charger, fully charged
# State 3: not on charger, battery starting to get low
# State 4: not on charger, good battery - freeplay active
# State 5: battery low, looking for charger
# State 6: battery low and we know where the charger is, moving to dock and docking
# State 9: Cozmo is on its side or is currently picked up
# State 0: recovery state - used to smooth state switching and to reassess which state Cozmo should be in
#
# States dictate what Cozmo does. In state 4 Cozmo will enter freeplay mode, exploring and interacting with his environment: 
# stack cubes, build pyramids, offer people he sees fistbumps and games of peekaboo, and more. When his battery drops below 
# a certain threshold (set in the variable lowbatvoltage), he will start looking for his charger (state 5). 
# If he finds it he will attempt to dock  (state 6) and start charging (state 1). Once fully charged (state 2), he drives off
# the charger and the cycle repeats (state 4). State 3 is used as a 'delay' so a single drop in battery level won't
# immediately cause him to seek out his charger. States 9 and 0 handle being picked up, falling, being on his side, and eventual
# recovery.
#
# The battery level of Cozmo is also used to manipulate his three "needs" settings: repair, energy, play (the three metrics for
# 'happiness' that you see in the main screen of the Anki Cozmo app). As his battery level gets lower so will his overall mood 
# and innate reactions to events. (TLDR: he gets grumpier the lower his battery level is)
#
# An event monitor running in a seperate thread watches for events like being picked up, seeing a face, detecting a cliff, etc.
# Some events are just logged, others trigger different Cozmo states or actions.
#


#import required functions
import sys, os, datetime, random, time, math, re, threading
import asyncio, cozmo, cozmo.objects, cozmo.util
from cozmo.util import degrees, distance_mm, speed_mmps, Pose
from cozmo.objects import CustomObject, CustomObjectMarkers, CustomObjectTypes

#external libraries used for camera annotation
#you will need to add these using pip/pip3
from PIL import ImageDraw, ImageFont
import numpy as np


# set up global variables
global robot
global freeplay
global tempfreeplay
global needslevel
global cozmostate
global scheduler_playokay
global msg
global start_time
global use_cubes
global charger
global highbatvoltage
global lowbatvoltage
global use_scheduler
global camera
global foundcharger
# initialize needed variables
freeplay = 0
robot = cozmo.robot.Robot


msg = 'No status'
q = None # dependency on queue variable for messaging instead of printing to event-content directly
thread_running = False # starting thread for custom events

#
#============================
# CONFIGURABLE VARIABLES HERE
#============================
# low battery voltage - when voltage drops below this Cozmo will start looking for his charger
# tweak this to suit your cozmo
lowbatvoltage = 3.7
highbatvoltage=4.14
# whether or not to activate the cubes (saves battery if you don't)
# I almost always leave this off, he will still stack them and mess around with them
use_cubes = 1
#
# whether or not to use the schedule to define allowed "play times"
# this code is a bit rough, use at your own risk
use_scheduler = 0
# 
# END OF CONFIGURABLE VARIABLES
#


#
# CAMERA ANNOTATOR
#
#
@cozmo.annotate.annotator
def camera_info(image, scale, annotator=None, world=None, **kw):
	global camera
	d = ImageDraw.Draw(image)
	bounds = [3, 0, image.width, image.height]

	camera = world.robot.camera
	text_to_display = 'Exposure: %s ms\n' % camera.exposure_ms
	text_to_display += 'Gain: %.3f\n' % camera.gain
	text = cozmo.annotate.ImageText(text_to_display,position=cozmo.annotate.TOP_LEFT,line_spacing=2,color="white",outline_color="black", full_outline=True)
	text.render(d, bounds)

		
#
# MAIN PROGRAM LOOP START
#
def cozmo_unleashed(robot: cozmo.robot.Robot):
	os.system('cls' if os.name == 'nt' else 'clear')
	global cozmostate,freeplay,start_time,needslevel,scheduler_playokay,use_cubes, charger, lowbatvoltage, highbatvoltage, use_scheduler,msg, camera, foundcharger, tempfreeplay
	#robot.world.charger = None
	#charger = None
	foundcharger = 0
	robot.set_robot_volume(0.2)
	# set up some camera stuff
	robot.world.image_annotator.add_annotator('camera_info', camera_info)
	camera = robot.camera
	camera.enable_auto_exposure()
	robot.enable_facial_expression_estimation(enable=True)
	if use_cubes == 0:
		robot.world.disconnect_from_cubes()
	else:
		robot.world.connect_to_cubes()
	robot.enable_all_reaction_triggers(False)
	robot.enable_stop_on_cliff(True)
	q = None # dependency on queue variable for messaging instead of printing to event-content directly
	thread_running = False # starting thread for custom events
	robot.set_needs_levels(repair_value=1, energy_value=1, play_value=1)
	needslevel = 1
	tempfreeplay = 0
	lowbatcount=0
	
	cozmostate = 0
	#some custom objects that I printed out and use as virtual walls, if you don't have them don't worry about it, it won't affect the program
	wall_obj1 = robot.world.define_custom_wall(CustomObjectTypes.CustomType01, CustomObjectMarkers.Circles2,  340, 120, 44, 44, True)
	wall_obj2 = robot.world.define_custom_wall(CustomObjectTypes.CustomType02, CustomObjectMarkers.Circles4,  340, 120, 44, 44, True)
	wall_obj3 = robot.world.define_custom_wall(CustomObjectTypes.CustomType03, CustomObjectMarkers.Circles5,  340, 120, 44, 44, True)
	wall_obj4 = robot.world.define_custom_wall(CustomObjectTypes.CustomType04, CustomObjectMarkers.Triangles2,340, 120, 44, 44, True)
	wall_obj5 = robot.world.define_custom_wall(CustomObjectTypes.CustomType05, CustomObjectMarkers.Triangles3,340, 120, 44, 44, True)
	wall_obj6 = robot.world.define_custom_wall(CustomObjectTypes.CustomType06, CustomObjectMarkers.Hexagons2, 120, 340, 44, 44, True)
	wall_obj7 = robot.world.define_custom_wall(CustomObjectTypes.CustomType07, CustomObjectMarkers.Circles3,  120, 340, 44, 44, True)
	wall_obj8 = robot.world.define_custom_wall(CustomObjectTypes.CustomType08, CustomObjectMarkers.Hexagons3, 120, 340, 44, 44, True)

	# initialize event monitoring thread
	q = None
	monitor(robot, q)
	start_time = time.time()
	cozmostate=0
	robot_print_current_state('entering main loop')
# ENTERING STATE LOOP
	while True:
		#robot_print_current_state('main loop checkpoint')
#

#State 1: on charger, charging
		if (robot.is_on_charger == 1) and (robot.is_charging == 1):
			#robot_print_current_state('state 1 conditions met')
			if cozmostate != 1: # 1 is charging
				robot_print_current_state('switching to state 1')
				cozmostate = 1
				start_time = time.time()
				foundcharger = 0
				robot_set_backpacklights(65535)  # 65535 is blue
				if robot.is_freeplay_mode_active:
					robot.enable_all_reaction_triggers(False)
					robot.stop_freeplay_behaviors()
				freeplay = 0
				if use_cubes == 1:
					robot.world.disconnect_from_cubes()
				#robot.play_anim("anim_gotosleep_sleeploop_01").wait_for_completed()
				#robot.play_anim_trigger(cozmo.anim.Triggers.Sleeping, loop_count=1, in_parallel=False, num_retries=0, ignore_body_track=True, ignore_head_track=False, ignore_lift_track=True).wait_for_completed()
			##robot_set_needslevel()
			#robot.play_anim_trigger(cozmo.anim.Triggers.Sleeping, loop_count=1, in_parallel=True, num_retries=0, ignore_body_track=True, ignore_head_track=False, ignore_lift_track=True).wait_for_completed()

			lowbatcount=0
			robot_print_current_state('charging')
			# once in a while make random snoring noises
			robot_check_sleep_snoring()
#
#State 2: on charger, fully charged
#
		if (robot.is_on_charger == 1) and (robot.is_charging == 0):
			robot_print_current_state('state 2 conditions met')
			if cozmostate != 2:  # 2 is fully charged
				robot_print_current_state('switching to state 2')
				cozmostate = 2
				lowbatcount=0
				foundcharger = 0
				if use_cubes == 1:
					robot.world.connect_to_cubes()
				robot_set_backpacklights(16711935)  # 16711935 is green
			robot.set_needs_levels(repair_value=1, energy_value=1, play_value=1)
			##robot_set_needslevel()
			robot_print_current_state('fully charged')
			robot_check_scheduler()
#
#State 3: not on charger, battery starting to get low
#
		# basic 'trigger guard' so Cozmo doesn't go to charger immediately if the voltage happens to dip below 3.7
		if (robot.battery_voltage <= lowbatvoltage) and (robot.is_on_charger == 0) and cozmostate != 5 and cozmostate != 6 and cozmostate != 9:
			robot_print_current_state('state 3 conditions met')
			lowbatcount += 1
			robot_set_needslevel()
			robot_print_current_state('battery getting low')
			robot_reaction_chance(cozmo.anim.Triggers.CodeLabTakaTaka,1,False,False,False)
			time.sleep(0.5)
		# if we dip below the threshold three times we switch to state 5
		if lowbatcount > 2 and (robot.is_on_charger == 0) and cozmostate !=5 and cozmostate !=6:
			if use_cubes == 1:
				robot.world.disconnect_from_cubes()
			robot_set_needslevel()
			robot_print_current_state('switching to state 5')
			robot_set_backpacklights(4278190335)  # 4278190335 is red
			cozmostate = 5
#			
#State 4: not on charger, good battery - freeplay active
#
		if (robot.battery_voltage > lowbatvoltage) and (robot.is_on_charger == 0) and cozmostate != 9 and cozmostate != 5 and cozmostate != 6 and cozmostate != 3:
			#robot_print_current_state('state 4 conditions met')
			if cozmostate != 4: # 4 is freeplay
				cozmostate = 4
				robot_print_current_state('switching to state 4')
				robot_set_backpacklights(16711935)  # 16711935 is green
				#initiate freeplay
				if freeplay == 0:
					freeplay = 1
					start_time = time.time()
					try:
						robot.drive_wheels(40, 40, l_wheel_acc=50, r_wheel_acc=50, duration=1)
					except:
						pass
					robot_reaction_chance(cozmo.anim.Triggers.OnSpeedtapGameCozmoWinHighIntensity,1,True,True,False)
					robot_print_current_state('entering freeplay state')
					if use_cubes == 1:
						robot.world.connect_to_cubes()
					if not robot.is_freeplay_mode_active:
						robot.enable_all_reaction_triggers(True)
						robot.start_freeplay_behaviors()
			freeplay = 1
			if not robot.is_freeplay_mode_active and cozmostate == 4 and freeplay == 1:
				robot.enable_all_reaction_triggers(True)
				robot_print_current_state('freeplay re-enabling for state 4')
				robot.start_freeplay_behaviors()
			robot_print_current_state('freeplay mode')
			robot_set_needslevel()
			robot_check_randomreaction()

#
# state 5: battery low, looking for charger
#
		if cozmostate == 5 and tempfreeplay != 1:
			robot_print_current_state('state 5 conditions met')
			if robot.is_freeplay_mode_active:
				robot.enable_all_reaction_triggers(True)
				robot.stop_freeplay_behaviors()
			robot.enable_all_reaction_triggers(True)
			robot_locate_dock()
			freeplay = 0
			robot_locate_dock()

#
# state 6: battery low and we know where the charger is, moving to dock and docking
#
		if cozmostate == 6:
			robot_print_current_state('state 6 conditions met')
			if robot.is_freeplay_mode_active:
				robot.enable_all_reaction_triggers(False)
				robot.stop_freeplay_behaviors()
				freeplay = 0
			robot_print_current_state('initiating docking')
			robot.abort_all_actions(log_abort_messages=True)
			#robot.wait_for_all_actions_completed()
			freeplay = 0
			##robot_set_needslevel()
			robot_start_docking()

#
# state 9: we're on our side or are currently picked up
#
		if cozmostate == 9:
			robot_print_current_state('state 9 conditions met')
			robot_flash_backpacklights(4278190335)  # 4278190335 is red
			#robot_reaction_chance(cozmo.anim.Triggers.CodeLabUnhappy,1,True,False,False)
			while cozmostate == 9:
				robot_print_current_state('picked up or on side')
				##robot_set_needslevel()
				if not robot.is_falling and not robot.is_picked_up:
					robot_print_current_state('state reset - switching to 0')
					cozmostate == 0
					break
				if robot.is_freeplay_mode_active:
					robot_print_current_state('disabling freeplay')
					robot.enable_all_reaction_triggers(False)
					robot.stop_freeplay_behaviors()
					freeplay = 0
				robot.abort_all_actions(log_abort_messages=True)
				#robot.wait_for_all_actions_completed()
				robot_reaction_chance(cozmo.anim.Triggers.AskToBeRightedLeft,1,False,False,False)
				robot_print_current_state('picked annoyed response 1')
				time.sleep(0.5)
				if not robot.is_falling and not robot.is_picked_up:
					robot_print_current_state('state reset - switching to 0')
					cozmostate == 0
					break
				robot_reaction_chance(cozmo.anim.Triggers.TurtleRoll,1,False,False,False)
				robot_print_current_state('picked annoyed response 2')
				time.sleep(0.5)
				if not robot.is_falling and not robot.is_picked_up:
					robot_print_current_state('state reset - switching to 0')
					cozmostate == 0
					break
				robot_reaction_chance(cozmo.anim.Triggers.CodeLabUnhappy,1,True,False,False)
				robot_print_current_state('picked annoyed response 3')
				time.sleep(0.5)
				# time.sleep(1)
				robot_print_current_state('state 9 loop segment complete')

#
# state 0: recovery state
#		
		if cozmostate == 0:
			robot_print_current_state('state 0 conditions met')
			robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,True,True,True)
			robot.set_all_backpack_lights(cozmo.lights.white_light)
			time.sleep(0.5)
#			
# we have looped through the states
#
		#robot_set_needslevel()
		#robot_reaction_chance(cozmo.anim.Triggers.CodeLabChatty,99,True,True,False)
		#msg = 'state loop complete'
		#robot_print_current_state('cozmo_unleashed state program loop complete')
		time.sleep(0.5)
#
# end of loop
	##robot_set_needslevel()
	robot_reaction_chance(cozmo.anim.Triggers.CodeLabTakaTaka,1,True,True,False)
	robot_print_current_state('exiting main loop - how did we get here?')
#
# END OF MAIN PROGRAM LOOP
#
# ROBOT FUNCTIONS
#
def robot_set_backpacklights(color):
	global robot
	robot.set_backpack_lights_off()
	color1=cozmo.lights.Color(int_color=color, rgb=None, name=None)
	color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
	light1=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=2000, off_period_ms=1000, transition_on_period_ms=1500, transition_off_period_ms=500)
	light2=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=2000)
	light3=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=2000, transition_on_period_ms=500, transition_off_period_ms=1500)
	robot.set_backpack_lights(None, light1, light2, light3, None)

def robot_flash_backpacklights(color):
	global robot
	robot.set_backpack_lights_off()
	color1=cozmo.lights.Color(int_color=color, rgb=None, name=None)
	color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
	light3=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=500, off_period_ms=250, transition_on_period_ms=375, transition_off_period_ms=125)
	light2=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=250, off_period_ms=250, transition_on_period_ms=250, transition_off_period_ms=500)
	light1=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=250, off_period_ms=500, transition_on_period_ms=125, transition_off_period_ms=375)
	robot.set_backpack_lights(None, light1, light2, light3, None)	

def robot_set_needslevel():
	global robot, needslevel, msg
	needslevel = 1 - (4.05 - robot.battery_voltage)
	if needslevel < 0.1:
		needslevel = 0.1
	if needslevel > 1:
		needslevel = 1
	i = random.randint(1, 1000)
	if i >= 990:
		robot_print_current_state('updating needs levels')
		robot.set_needs_levels(repair_value=needslevel, energy_value=needslevel, play_value=needslevel)

def robot_check_sleep_snoring():
	global robot
	i = random.randint(1, 1000)
	if i >= 995:
		robot_print_current_state('playing big snore')
		try:
			robot.play_anim("anim_guarddog_fakeout_02").wait_for_completed()
		except:
			robot_print_current_state('big snore anim failed')
			pass
		try:
			robot.play_anim("anim_gotosleep_sleeploop_01").wait_for_completed()
		except:
			robot_print_current_state('small snore anim failed')
			pass
	elif i >= 985:
			robot_print_current_state('playing small snore')
			try:
				robot.play_anim("anim_gotosleep_sleeploop_01").wait_for_completed()
			except:
				robot_print_current_state('small snore anim failed')
				pass
	else:
		#robot_print_current_state('check complete - no snore')
		time.sleep(0.5)

def robot_check_randomreaction():
	global robot,cozmostate,freeplay
	i = random.randint(1, 1000)
	if i >= 970 and not robot.is_carrying_block and not robot.is_picking_or_placing and not robot.is_pathing and cozmostate==4:
		#random action!
		robot_print_current_state('random animation starting')
		if robot.is_freeplay_mode_active:
			robot.enable_all_reaction_triggers(False)
			robot.stop_freeplay_behaviors()
		robot.abort_all_actions(log_abort_messages=True)
		#robot.wait_for_all_actions_completed()
		# grab a list of animation triggers
		all_animation_triggers = robot.anim_triggers
		# randomly shuffle the animations
		random.shuffle(all_animation_triggers)
		# select the first animation from the shuffled list
		triggers = 1
		chosen_triggers = all_animation_triggers[:triggers]
		print('Playing {} random animations:'.format(triggers))
		for trigger in chosen_triggers:
			if 'Onboarding' in trigger:
				trigger = 'SparkSuccess'
			print("trigger %s" %str(trigger)," executed")
			robot_print_current_state('playing random animation')
			try:
				robot.play_anim_trigger(trigger).wait_for_completed()
			except:
				robot_print_current_state('random animation play failed')
				pass
			robot_print_current_state('played random animation')
		#robot.wait_for_all_actions_completed()	
		if freeplay == 1 and not robot.is_freeplay_mode_active:
			robot.enable_all_reaction_triggers(True)
			robot.start_freeplay_behaviors()
		time.sleep(0.5)

def robot_check_scheduler():
	global robot,scheduler_playokay,use_cubes,use_scheduler, highbatvoltage
	# from 7pm on weekdays
	weekdaystartplay = 19
	# to 11pm on weekdays
	weekdaystopplay  = 23
	# from 7am on weekends
	weekendstartplay = 7
	# to 11pm on weekends
	weekendstopplay  = 23
	# scheduler - when battery is charged this represents the chance cozmo will get off his charger to play
	# chance is defined as a number between 1-99 with a higher number representing a lesser chance
	playchance = 1
	robot_print_current_state('starting schedule check')
	# day and time check - are we okay to play at this time and day?
	day_of_week = datetime.date.today().weekday() # 0 is Monday, 6 is Sunday
	ctime = datetime.datetime.now().time()
	scheduler_playokay=0
	#it's weekend! Check for allowed times.
	if day_of_week > 4:
		if (ctime > datetime.time(weekendstartplay) and ctime < datetime.time(weekendstopplay)):
			scheduler_playokay=1
	#it's a weekday! Check for allowed times.
	else:
		if (ctime > datetime.time(weekdaystartplay) and ctime < datetime.time(weekdaystopplay)):
			scheduler_playokay=1
	# are we using the scheduler?
	if use_scheduler==0:
		scheduler_playokay=1
	# if the schedule says OK roll dice to see if we wake up
	if scheduler_playokay==1:
		robot_print_current_state('schedule OK - random chance to wake up')
		i = random.randint(1, 100)
		# wake up chance
		if use_scheduler==0:
			i = 100
		if i >= playchance:
			robot_print_current_state('waking up - leaving charger')
			#robot.world.connect_to_cubes()
			#robot_set_backpacklights(16711935)  # 16711935 is green
			try:
				robot.play_anim("anim_gotosleep_getout_02").wait_for_completed()
			except:
				robot_print_current_state('wake up anim failed')
				pass
			for _ in range(3):
				try:
					robot.drive_off_charger_contacts().wait_for_completed()
					robot_print_current_state('drive off charger OK')
				except: 
					robot_print_current_state('drive off charger error')
					pass
			time.sleep(0.5)
			highbatvoltage = robot.battery_voltage
			try:
				robot.move_lift(-3)
			except:
				robot_print_current_state('lift reset fail')
				pass
			try:
				robot.drive_straight(distance_mm(60), speed_mmps(50)).wait_for_completed()
			except:
				robot_print_current_state('drive straight fail')
				pass
			try:
				robot.drive_straight(distance_mm(100), speed_mmps(50)).wait_for_completed()
			except:
				robot_print_current_state('drive straight fail')
				pass
	# we're out of schedule or didn't make the dice roll, back off and check again later.
	x = 1
	while x < 20 and (robot.is_on_charger == 1):
		if scheduler_playokay == 1:
			robot_print_current_state('battery charged - schedule ok - not active')
			time.sleep(1)
		else:
			#print("State:  charged,  not active by schedule, sleep loop %d of 30 before next check." % (x))
			robot_print_current_state('battery charged - out of schedule')
			time.sleep(1)
			robot_check_sleep_snoring()
		if (robot.is_on_charger == 0):
			robot_print_current_state('cozmo was removed from charger')
			break
		time.sleep(2)

def robot_print_current_state(currentstate):
	global robot,needslevel,start_time,cozmostate,msg, highbatvoltage
	##robot_set_needslevel()
	os.system('cls' if os.name == 'nt' else 'clear')
	#msg=robot.current_behavior
	print("State          : %s" %currentstate)
	print("Internal state : %s"% cozmostate)
	print("High Battery   : %s" % str(round(highbatvoltage, 2))) 
	print("Battery        : %s" % str(round(robot.battery_voltage, 2)))
	print("Energy         : %s" % round(needslevel, 2))
	print("Runtime        : %s" % round(((time.time() - start_time)/60),2))
	#print("Cubes connected: %s" % robot.world.World.active_behavior.connected_light_cubes)
	print("Event message  : %s" %msg)
	#print("State: %s" %currentstate,"battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2)," runtime %s" % round(((time.time() - start_time)/60),2)," internal state %s"% cozmostate," last message: %s" %msg)
	
def robot_reaction_chance(animation,chance,ignorebody,ignorehead,ignorelift):
	global robot, msg, freeplay
	i = random.randint(1, 100)
	if i >= chance:
		robot_print_current_state('starting animation')
		oldfreeplay = 0
		if freeplay == 1:
			if robot.is_freeplay_mode_active:
				robot_print_current_state('disabling freeplay')
				robot.enable_all_reaction_triggers(False)
				robot.stop_freeplay_behaviors()
			oldfreeplay = 1
			freeplay = 0
		robot.abort_all_actions(log_abort_messages=True)
		robot_print_current_state('action queue aborted')
		#robot.wait_for_all_actions_completed()
		try:
			robot.play_anim_trigger(animation, ignore_body_track=ignorebody, ignore_head_track=ignorehead, ignore_lift_track=ignorelift).wait_for_completed()
			print("reaction %s" %str(animation)," executed")
			#msg = ("reaction %s" %str(animation)," executed")
			robot_print_current_state('random animation completed')
		except:
			robot_print_current_state('play animation failed')
			#print("reaction %s" %str(animation)," aborted")
		#robot.wait_for_all_actions_completed()
		try:
			robot.set_head_angle(degrees(0)).wait_for_completed()
		except:
			robot_print_current_state('head angle reset failed')
			pass
		#robot.wait_for_all_actions_completed()
		try:
			robot.move_lift(-3)
		except:
			robot_print_current_state('lift move down failed')
			pass
		if oldfreeplay == 1:
			oldfreeplay = 0
			freeplay = 1
			robot_print_current_state('re-enabling freeplay')
			if not robot.is_freeplay_mode_active:
				robot.enable_all_reaction_triggers(True)
				robot.start_freeplay_behaviors()
	else:
		time.sleep(0.5)
		robot_print_current_state('animation check - no winner')

def robot_locate_dock():
	global cozmostate,freeplay,start_time,needslevel,scheduler_playokay,use_cubes, charger, lowbatvoltage, use_scheduler,msg, camera, foundcharger, tempfreeplay
	#back off from whatever we were doing
	robot_set_backpacklights(4278190335)  # 4278190335 is red
	if robot.is_freeplay_mode_active:
		robot_print_current_state('disabling freeplay')
		robot.stop_freeplay_behaviors()
	robot.enable_all_reaction_triggers(True)
	robot.abort_all_actions(log_abort_messages=True)
	robot_print_current_state('all actions aborted')
	#robot.wait_for_all_actions_completed()
	if use_cubes==1:
		robot.world.disconnect_from_cubes()
	freeplay = 0
	robot_reaction_chance(cozmo.anim.Triggers.NeedsMildLowEnergyRequest,1,False,False,False)
	try:
		robot.drive_straight(distance_mm(-30), speed_mmps(50)).wait_for_completed()
	except:
		robot_print_current_state('drive straight failed')
		pass
	##robot_set_needslevel()
	robot_print_current_state('finding charger')
	# charger location search
	if not robot.world.charger:
		charger = None
		robot.world.charger = None
		cozmostate=5
	# see if we already know where the charger is
	if robot.world.charger:
		if robot.world.charger.pose.is_comparable(robot.pose):
			charger = robot.world.charger
			#we know where the charger is
			robot_print_current_state('finding charger, charger position known')
			robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,True,False,False)
			time.sleep(0.5)
			cozmostate = 6
			foundcharger = 1
		else:
			robot_print_current_state('finding charger, charger not in expected location')
			charger = None
			robot.world.charger = None
			cozmostate=5
			pass
	if not charger:
		robot_print_current_state('looking for charger')
		cozmostate=5
		robot_reaction_chance(cozmo.anim.Triggers.SparkIdle,30,True,True,True)
		try:
			robot.move_lift(-3)
		except:
			pass
		try:
			robot.set_head_angle(degrees(0)).wait_for_completed()
		except:
			pass
		try:
			robot.drive_straight(distance_mm(-20), speed_mmps(50)).wait_for_completed()
		except:
			pass
		# randomly drive around for a bit and see if we can spot the charger
		robot_drive_random_pattern()
		robot_print_current_state('looking for charger, random drive loop complete')
	time.sleep(0.5)

def robot_start_docking():
	global cozmostate,freeplay,start_time,needslevel,scheduler_playokay,use_cubes, charger, lowbatvoltage, use_scheduler,msg, camera, foundcharger
	#charger = robot.world.charger
	#action = robot.go_to_object(charger, distance_mm(65.0))
	#action.wait_for_completed()
	#robot_print_current_state('go to object complete')
	action = robot.go_to_pose(robot.world.charger.pose)
	action.wait_for_completed()
	robot_print_current_state('go to pose complete')
	robot.drive_straight(distance_mm(-50), speed_mmps(50)).wait_for_completed()
	robot_print_current_state('drove back a little bit')
	if not robot.world.charger:
		# we can't see it. Remove charger from navigation map and quit this loop.
		robot.world.charger = None
		charger = None
		cozmostate=5
		try:
			robot.play_anim_trigger(cozmo.anim.Triggers.ReactToPokeReaction, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=True).wait_for_completed()
		except:
			pass
		#os.system('cls' if os.name == 'nt' else 'clear')
		robot_print_current_state('charger not found, clearing map')
		round(((time.time() - start_time)/60),2)
		cozmostate = 5
	dockloop = 0
	while dockloop < 2 and cozmostate ==6 and robot.world.charger:
		action = robot.go_to_pose(robot.world.charger.pose)
		action.wait_for_completed()
		#robot_print_current_state('I should be in front of the charger')
		robot.set_head_light(False)
		time.sleep(0.5)
		robot.set_head_light(True)
		time.sleep(0.5)
		robot.set_head_light(False)
		if not robot.world.charger:
			charger = None
			robot.world.charger = None
			cozmostate=5
			break
			# # we can't see it. Remove charger from navigation map and quit this loop.
			# robot.world.charger = None
			# charger = None
			# robot.play_anim_trigger(cozmo.anim.Triggers.ReactToPokeReaction, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=True).wait_for_completed()
			# #os.system('cls' if os.name == 'nt' else 'clear')
			# print("State:  charger not found, clearing map. battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2)," runtime %s" % round(((time.time() - start_time)/60),2))
			#cozmostate = 5
			# break
		# try:
			# action = robot.go_to_pose(charger.pose)
			# action.wait_for_completed()
		# except:
			# pass
		
		try:
			robot.drive_straight(distance_mm(-20), speed_mmps(50)).wait_for_completed()
		except:
			pass
		action = robot.go_to_pose(robot.world.charger.pose)
		action.wait_for_completed()
		try:
			robot.drive_straight(distance_mm(-20), speed_mmps(50)).wait_for_completed()
		except:
			pass
		robot_reaction_chance(cozmo.anim.Triggers.FeedingReactToShake_Normal,85,True,False,False)
		robot_print_current_state('docking')
		robot.turn_in_place(degrees(95)).wait_for_completed()
		robot.turn_in_place(degrees(95)).wait_for_completed()
		time.sleep(0.5)
		robot_reaction_chance(cozmo.anim.Triggers.CubePounceFake,1,True,False,False)
		robot.drive_straight(distance_mm(-145), speed_mmps(150)).wait_for_completed()
		time.sleep(0.5)
		# check if we're now docked
		if robot.is_on_charger:
			# Yes! we're docked!
			cozmostate = 1
			# robot_set_backpacklights(65535) # blue
			# try:
				# robot.play_anim("anim_sparking_success_02").wait_for_completed()
			# except:
				# pass
			# try:
				# robot.set_head_angle(degrees(0)).wait_for_completed()
			# except:
				# pass
			# robot_print_current_state('docked')
			# try
				# robot.play_anim("anim_gotosleep_getin_01").wait_for_completed()
			# except:
				# pass
			# try:
				# play_anim("anim_gotosleep_sleeping_01").wait_for_completed()
			# except:
				# pass
			dockloop = 3
			break
		# No, we missed. Back off and try again
		elif robot.world.charger:
			robot_print_current_state('failed to dock')
			robot_reaction_chance(cozmo.anim.Triggers.AskToBeRightedRight,1,True,False,False)
			try:
				robot.move_lift(-3)
			except:
				pass
			try:
				robot.set_head_angle(degrees(0)).wait_for_completed()
			except:
				pass
			#os.system('cls' if os.name == 'nt' else 'clear')
			robot_print_current_state('failed to dock, retrying')
			try:
				robot.drive_straight(distance_mm(50), speed_mmps(50)).wait_for_completed()
			except:
				pass
			try:
				robot.turn_in_place(degrees(-3)).wait_for_completed()
			except:
				pass
			try:
				robot.drive_straight(distance_mm(100), speed_mmps(50)).wait_for_completed()
			except:
				pass
			try:
				robot.turn_in_place(degrees(94)).wait_for_completed()
			except:
				pass
			try:
				robot.turn_in_place(degrees(95)).wait_for_completed()
			except:
				pass
			try:
				robot.set_head_angle(degrees(0)).wait_for_completed()
			except:
				pass
		charger= None
		robot.world.charger=None
		cozmostate=5
		time.sleep(0.5)
		dockloop+=1
	# express frustration
	try:
		robot.drive_straight(distance_mm(50), speed_mmps(50)).wait_for_completed()
	except:
		pass
	try:
		robot.turn_in_place(degrees(-3)).wait_for_completed()
	except:
		pass
	try:
		robot.drive_straight(distance_mm(80), speed_mmps(50)).wait_for_completed()
	except:
		pass
	robot_drive_random_pattern()
	robot_reaction_chance(cozmo.anim.Triggers.MemoryMatchPlayerWinGame,1,True,False,False)
	x=0
	while x<11 and cozmostate == 5:
		tempfreeplay = 1
		if freeplay==0:
			freeplay = 1
			robot_print_current_state('charger not found, falling back to freeplay')
			robot_set_backpacklights(16711935) # green
			if use_cubes==1:
				robot.world.connect_to_cubes()
			if not robot.is_freeplay_mode_active:
				robot_print_current_state('freeplay enabled')
				robot.enable_all_reaction_triggers(True)
				robot.start_freeplay_behaviors()
		if cozmostate != 5:
			break
		#robot_print_current_state('charger not found, falling back to freeplay')
		time.sleep(1)
		
		if robot.world.charger:
			robot_print_current_state('found charger while in temporary freeplay')
			charger = robot.world.charger
			cozmostate = 6
			break
		
		time.sleep(1)
		x+=1
	#after 100 seconds or spotting the charger end freeplay
	tempfreeplay = 0
	if robot.is_freeplay_mode_active:
		robot.enable_all_reaction_triggers(False)
		robot.stop_freeplay_behaviors()
	if use_cubes==1:
		robot.world.disconnect_from_cubes()
	robot_set_backpacklights(4278190335) # red
	freeplay = 0
	cozmostate = 5
	#os.system('cls' if os.name == 'nt' else 'clear')
	robot_print_current_state('temporary freeplay ended')
	time.sleep(1)
						
def robot_drive_random_pattern():
	global cozmostate,freeplay,start_time,needslevel,scheduler_playokay,use_cubes, charger, lowbatvoltage, use_scheduler,msg, camera, foundcharger
	loops=5
	while loops>0 and cozmostate == 5:
		# if robot.world.charger and robot.world.charger.pose.is_comparable(robot.pose):
			# loops=0
			# charger = robot.world.charger
			# robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,True,True,True)
			# robot_print_current_state('found charger breaking')
			# cozmostate = 6
			# foundcharger = 1
			# break
		# drive to a random point and orientation
		counter=0
		while counter < 2 and cozmostate ==5:
			if random.choice((True, False)):
				x=150
			else:
				x=-150
			if random.choice((True, False)):
				y=150
			else:
				y=-150
			z= random.randrange(-40, 41, 1)
			robot_print_current_state('looking for charger, going to random pose')
			try:
				robot.go_to_pose(Pose(x, y, 0, angle_z=degrees(z)), relative_to_robot=True).wait_for_completed()
				robot.set_head_light(False)
				time.sleep(0.25)
				robot.set_head_light(True)
				time.sleep(0.25)
				robot.set_head_light(False)
			except:
				pass
			if cozmostate == 6:
				break
			# if robot.world.charger and robot.world.charger.pose.is_comparable(robot.pose):
				# loops=0
				# charger = robot.world.charger
				# cozmostate = 6
				# foundcharger = 1
				# robot_print_current_state('found charger, breaking')
				# robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,True,False,False)
				# break
			# else:
			robot_check_randomreaction()
			counter+=1
		# turn around for a bit
		time.sleep(0.5)
		counter=0
		while counter <2 and cozmostate == 5:
			a= random.randrange(8, 17, 8)
			t= random.randrange(2, 4, 1)
			if random.choice((True, False)):
				rx=40
			else:
				rx=-40
			ry=-rx
			robot_print_current_state('looking for charger, rotating')
			try:
				robot.set_head_light(False)
				time.sleep(0.2)
				robot.set_head_light(True)
				time.sleep(0.2)
				robot.set_head_light(False)
				robot.drive_wheels(rx, ry, l_wheel_acc=a, r_wheel_acc=a, duration=t)
				time.sleep(0.5)
			except:
				pass
			if cozmostate == 6:
				break
			# if robot.world.charger and robot.world.charger.pose.is_comparable(robot.pose):
				# loops=0
				# charger = robot.world.charger
				# robot_print_current_state('found charger')
				# foundcharger = 1
				# robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,True,False,False)
				# break
			# else:
			robot_check_randomreaction()
			counter+=1
		
		# if charger:
			# loops=0
			# charger = robot.world.charger
			# cozmostate = 6
			# foundcharger = 1
			# robot_print_current_state('found charger')
			# robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,True,False,False)
			# break
		##robot_set_needslevel()
		robot_print_current_state('looking for charger, looping through random poses')
		loops=loops-1
	robot_print_current_state('looking for charger, broke out of drive loop')
	#return charger

#
# END OF ROBOT FUNCTIONS
#

	
#
# EVENT MONITOR FUNCTIONS
#
class CheckState (threading.Thread):
	global robot,cozmostate,freeplay,msg,camera
	def __init__(self, thread_id, name, _q):
		threading.Thread.__init__(self)
		self.threadID = thread_id
		self.name = name
		self.q = _q

# main thread
	def run(self):
		global robot,cozmostate,freeplay,msg,camera,highbatvoltage,lowbatvoltage
		delay = 10
		is_picked_up = False
		is_falling = False
		is_on_charger = False
		is_cliff_detected = False
		is_moving = False
		is_carrying_block = False
		is_localized = False
		is_picking_or_placing = False
		is_pathing = False
		while thread_running:
			
# event monitor: robot is picked up detection
			

			if robot.is_picked_up:
				delay = 0
				if not is_picked_up:
					is_picked_up = True
					robot_flash_backpacklights(4278190335)  # 4278190335 is red
					robot_print_current_state('cozmo.robot.Robot.is_pickup_up: True')
					cozmostate = 9
			elif is_picked_up and delay > 9:
				cozmostate = 0
				is_picked_up = False
				robot_print_current_state('cozmo.robot.Robot.is_pickup_up: False')
			elif delay <= 9:
				delay += 1
				
# event monitor: robot is carrying a block

			if robot.is_carrying_block:
				if not is_carrying_block:
					is_carrying_block = True
					robot_print_current_state('cozmo.robot.Robot.is_carrying_block: True')
			elif not robot.is_carrying_block:
				if is_carrying_block:
					is_carrying_block = False
					robot_print_current_state('cozmo.robot.Robot.is_carrying_block: False')

# event monitor: robot is localized (I don't think this is working right now)

			# if robot.is_localized:
				# if not is_localized:
					# is_localized = True
					# robot_print_current_state('cozmo.robot.Robot.is_localized: True')
			# elif not robot.is_localized:
				# if is_localized:
					# is_localized = False
					# robot_print_current_state('cozmo.robot.Robot.is_localized: False')				

# event monitor: robot is falling

			if robot.is_falling:
				if not is_falling:
					is_falling = True
					robot_print_current_state('cozmo.robot.Robot.is_falling: True')	
					cozmostate = 9
			elif not robot.is_falling:
				if is_falling:
					is_falling = False
					robot_print_current_state('cozmo.robot.Robot.is_falling: False')

# event monitor: robot moves onto charger

			if robot.is_on_charger:
				if not is_on_charger:
					is_on_charger = True
					freeplay = 0
					if robot.is_freeplay_mode_active:
						robot.enable_all_reaction_triggers(False)
						robot.stop_freeplay_behaviors()
					robot.abort_all_actions(log_abort_messages=True)
					#robot.wait_for_all_actions_completed()
					msg = 'cozmo.robot.Robot.is_on_charger: True'
					# robot_set_backpacklights(65535)  # 65535 is blue
					# #robot.play_anim_trigger(cozmo.anim.Triggers.Sleeping, loop_count=1, in_parallel=True, num_retries=0, ignore_body_track=True, ignore_head_track=False, ignore_lift_track=True).wait_for_completed()
					# try:
						# robot.play_anim_trigger(cozmo.anim.Triggers.GoToSleepGetIn).wait_for_completed()
					# except:
						# pass
					robot_set_backpacklights(65535) # blue
					if cozmostate==1:
						try:
							robot.play_anim("anim_sparking_success_02").wait_for_completed()
						except:
							pass
						try:
							robot.set_head_angle(degrees(0)).wait_for_completed()
						except:
							pass
						robot_print_current_state('docked')
					try:
						robot.play_anim("anim_gotosleep_getin_01").wait_for_completed()
					except:
						pass
					try:
						play_anim("anim_gotosleep_sleeping_01").wait_for_completed()
					except:
						pass
					
					#robot.play_anim_trigger(cozmo.anim.Triggers.StartSleeping, loop_count=1, in_parallel=True, num_retries=0, ignore_body_track=True, ignore_head_track=False, ignore_lift_track=True).wait_for_completed()
				if robot.is_charging:
					cozmostate = 1
					#robot_print_current_state('charging')
				else:
					cozmostate = 2
					robot_print_current_state('not charging')
					#print(msg)
			elif not robot.is_on_charger:
				if is_on_charger:
					robot_set_backpacklights(16711935)  # 16711935 is green
					is_on_charger = False
					cozmostate = 4
					msg = 'cozmo.robot.Robot.is_on_charger: False'
					robot_print_current_state('off charger')
					#print(msg)

# event monitor: robot has detected cliff

			if robot.is_cliff_detected and not robot.is_falling and not robot.is_picked_up:
				if not is_cliff_detected:
					is_cliff_detected = True
					wasinfreeplay = 0
					msg = 'cozmo.robot.Robot.is_cliff_detected: True'
					robot_print_current_state('cliff detected')
					#print(msg)
					if freeplay == 1:
						freeplay = 0
						wasinfreeplay = 1
						if robot.is_freeplay_mode_active:
							robot.enable_all_reaction_triggers(False)
							robot.stop_freeplay_behaviors()
						#robot.wait_for_all_actions_completed()
					robot.abort_all_actions(log_abort_messages=True)
					try:
						robot.drive_wheels(-40, -40, l_wheel_acc=30, r_wheel_acc=30, duration=1.5)
					except:
						pass
					try:
						robot.drive_wheels(-40, -40, l_wheel_acc=30, r_wheel_acc=30, duration=1.5)
					except:
						pass
					is_cliff_detected = False
					msg = 'cozmo.robot.Robot.is_cliff_detected: False'
					robot_print_current_state('cliff no longer detected')
					#print(msg)
			elif not robot.is_cliff_detected:
				if is_cliff_detected:
					is_cliff_detected = False
					if wasinfreeplay == 1:
						freeplay = 1
						wasinfreeplay = 0
						if robot.is_freeplay_mode_active:
							robot.enable_all_reaction_triggers(True)
							robot.start_freeplay_behaviors()

# event monitor: robot is picking or placing something
			if robot.is_picking_or_placing:
				if not is_picking_or_placing:
					is_picking_or_placing = True
					msg = 'cozmo.robot.Robot.is_picking_or_placing: True'
					#print(msg)
					robot_print_current_state('Robot.is_picking_or_placing: True')
			elif not robot.is_picking_or_placing:
				if is_picking_or_placing:
					is_picking_or_placing = False
					msg = 'cozmo.robot.Robot.is_picking_or_placing: False'
					robot_print_current_state('Robot.is_picking_or_placing: False')
					#print(msg)		
				
# event monitor: robot is pathing (traveling to a target)
			if robot.is_pathing:
				if not is_pathing:
					is_pathing = True
					msg = 'cozmo.robot.Robot.is_pathing: True'
					#print(msg)
					robot_print_current_state('Robot.is_pathing: True')
			elif not robot.is_pathing:
				if is_pathing:
					is_pathing = False
					msg = 'cozmo.robot.Robot.is_pathing: False'
					robot_print_current_state('Robot.is_pathing: False')
					#print(msg)	
				
# event monitor: robot is moving
# too spammy/unreliable

			# if robot.is_moving:
				# if not is_moving:
					# is_moving = True
					# robot_print_current_state('Robot.is_moving: True')
			# elif not robot.is_moving:
				# if is_moving:
					# is_moving = False
					# robot_print_current_state('Robot.is_moving: False')	

# end of detection loop
			# # camera IR control
			# if camera.exposure_ms < 60:
				# # robot.say_text("light").wait_for_completed()
				# robot.set_head_light(False)
			# elif camera.exposure_ms >= 60:
				# # robot.say_text("dark").wait_for_completed()
				# robot.set_head_light(True)
			time.sleep(0.1)

def print_prefix(evt):
	msg = evt.event_name + ' '
	return msg

def print_object(obj):
	if isinstance(obj,cozmo.objects.LightCube):
		cube_id = next(k for k,v in robot.world.light_cubes.items() if v==obj)
		msg = 'LightCube-' + str(cube_id)
	else:
		r = re.search('<(\w*)', obj.__repr__())
		msg = r.group(1)
	return msg

def monitor_generic(evt, **kwargs):
	global robot,cozmostate,freeplay,msg,camera
	msg = print_prefix(evt)
	if 'behavior' in kwargs or 'behavior_type_name' in kwargs:
		msg += kwargs['behavior_type_name'] + ' '
		msg += kwargs['behavior'] + ' '
	elif 'obj' in kwargs:
		msg += print_object(kwargs['obj']) + ' '
	elif 'action' in kwargs:
		action = kwargs['action']
		if isinstance(action, cozmo.anim.Animation):
			msg += action.anim_name + ' '
		elif isinstance(action, cozmo.anim.AnimationTrigger):
			msg += action.trigger.name + ' '
	else:
		msg += str(set(kwargs.keys()))
	robot_print_current_state('generic monitor data incoming')
	#print(msg)
#
# event monitor: robot is experiencing unexpected movement
#
def monitor_EvtUnexpectedMovement(evt, **kwargs):
	global robot,cozmostate,freeplay,msg,camera
	msg = kwargs
	robot_print_current_state('unexpected movement')
	#print(msg)
	if  cozmostate != 3 and cozmostate !=9:
		robot_print_current_state('unexpected behavior during action; aborting')
		#print("unexpected behavior during action; aborting")
		robot.abort_all_actions(log_abort_messages=True)
		robot.wait_for_all_actions_completed()
		#print("unexpected behavior during action; aborting")
		robot_print_current_state('unexpected behavior during action; aborting')
		
#
# event monitor: robot has started an action
#

#
# event monitor: robot has completed an action
#

def monitor_EvtActionCompleted(evt, action, state, failure_code, failure_reason, **kwargs):
	msg = print_prefix(evt)
	msg += print_object(action) + ' '
	if isinstance(action, cozmo.anim.Animation):
		msg += action.anim_name
	elif isinstance(action, cozmo.anim.AnimationTrigger):
		msg += action.trigger.name
	if failure_code is not None:
		msg += str(failure_code) + failure_reason
	robot_print_current_state('action completed')
#	print(msg)
#
# event monitor: an object was tapped
#
def monitor_EvtObjectTapped(evt, *, obj, tap_count, tap_duration, tap_intensity, **kwargs):
	msg = print_prefix(evt)
	msg += print_object(obj)
	msg += ' count=' + str(tap_count) + ' duration=' + str(tap_duration) + ' intensity=' + str(tap_intensity)
	print(msg)
	print(obj)
	#robot_print_current_state('object tapped')
	if str(obj) == "LightCube-1":
		print("cube1")
		#self.cube.set_lights(cozmo.lights.white_light.flash())
	if str(obj)  == "LightCube-2":
		print("cube1")
	if str(obj)  == "LightCube-3":
		print("cube1")
#
# event monitor: a face was detected
#
def monitor_face(evt, face, **kwargs):
	msg = print_prefix(evt)
	name = face.name if face.name is not '' else '[unknown face]'
	expression = face.expression if face.expression is not '' else '[unknown expression]'
	msg += name + ' face_id=' + str(face.face_id) + ' looking ' + str(face.expression)
	#print(msg)
	robot_print_current_state('face module')
#
# event monitor: an object started moving
#
def monitor_EvtBehaviorRequested(**kwargs):
	msg = (kwargs)
	robot_print_current_state('EvtBehaviorRequested')
	
def monitor_EvtObjectMovingStarted(evt, *, obj, acceleration, **kwargs):
	msg = print_prefix(evt)
	msg += print_object(obj) + ' '
	msg += ' accleration=' + str(acceleration)
	robot_print_current_state('object started moving')
	
#
# event monitor: an object stopped moving
#
def monitor_EvtObjectMovingStopped(evt, *, obj, move_duration, **kwargs):
	msg = print_prefix(evt)
	msg += print_object(obj) + ' '
	msg += ' move_duration ' + str(move_duration) + 'secs'
	#print(msg)
	robot_print_current_state('object stopped moving')
#
# event monitor: an object appeared in our vision
#
def monitor_EvtObjectAppeared(evt, **kwargs):
	global cozmostate,freeplay,start_time,needslevel,scheduler_playokay,use_cubes, charger, lowbatvoltage, use_scheduler,msg, camera, foundcharger
	msg = print_prefix(evt)
	msg += print_object(kwargs['obj']) + ' '
	if print_object(kwargs['obj']) == "Charger":
		charger = robot.world.charger
	if print_object(kwargs['obj']) == "Charger" and cozmostate == 5:
		robot_print_current_state('FOUND THE CHARGER')
		#print("it's the charger and we're looking for it!")
		cozmostate = 6
		charger = robot.world.charger
	robot_print_current_state('object appeared')

	  # cozmo.objects.EvtObjectDisappeared   : monitor_generic,
  # cozmo.objects.EvtObjectMovingStarted : monitor_EvtObjectMovingStarted,
  # cozmo.objects.EvtObjectMovingStopped : monitor_EvtObjectMovingStopped,
  # cozmo.objects.EvtObjectObserved      : monitor_generic,
  # cozmo.objects.EvtObjectTapped        : monitor_EvtObjectTapped,
  #cozmo.objects.EvtObjectAppeared      : monitor_EvtObjectAppeared,
  
dispatch_table = {
  
  cozmo.objects.EvtObjectTapped        : monitor_EvtObjectTapped,
  cozmo.objects.EvtObjectMovingStarted : monitor_EvtObjectMovingStarted,
  cozmo.objects.EvtObjectMovingStopped : monitor_EvtObjectMovingStopped,
  cozmo.faces.EvtFaceAppeared          : monitor_face,
  cozmo.faces.EvtFaceObserved          : monitor_face,
  cozmo.faces.EvtFaceDisappeared       : monitor_face,
  cozmo.robot.EvtUnexpectedMovement    : monitor_EvtUnexpectedMovement,
  cozmo.action.EvtActionCompleted      : monitor_EvtActionCompleted,
  cozmo.behavior.EvtBehaviorStarted    : monitor_generic,
  cozmo.behavior.EvtBehaviorStopped    : monitor_generic,
  cozmo.anim.EvtAnimationsLoaded       : monitor_generic,
  cozmo.anim.EvtAnimationCompleted     : monitor_generic,
}

excluded_events = {	# Occur too frequently to monitor by default
	cozmo.objects.EvtObjectObserved,
	cozmo.faces.EvtFaceObserved,
	cozmo.objects.EvtObjectAppeared,
	cozmo.objects.EvtObjectDisappeared,
	cozmo.behavior.EvtBehaviorRequested,
}

def monitor(_robot, _q, evt_class=None):
	if not isinstance(_robot, cozmo.robot.Robot):
		raise TypeError('First argument must be a Robot instance')
	if evt_class is not None and not issubclass(evt_class, cozmo.event.Event):
		raise TypeError('Second argument must be an Event subclass')
	global robot
	global q
	global thread_running
	robot = _robot
	q = _q
	thread_running = True
	if evt_class in dispatch_table:
		robot.world.add_event_handler(evt_class,dispatch_table[evt_class])
	elif evt_class is not None:
		robot.world.add_event_handler(evt_class,monitor_generic)
	else:
		for k,v in dispatch_table.items():
			if k not in excluded_events:
				robot.world.add_event_handler(k,v)
	thread_is_state_changed = CheckState(1, 'ThreadCheckState', q)
	thread_is_state_changed.start()

def unmonitor(_robot, evt_class=None):
	if not isinstance(_robot, cozmo.robot.Robot):
		raise TypeError('First argument must be a Robot instance')
	if evt_class is not None and not issubclass(evt_class, cozmo.event.Event):
		raise TypeError('Second argument must be an Event subclass')
	global robot
	global thread_running
	robot = _robot
	thread_running = False

	try:
		if evt_class in dispatch_table:
			robot.world.remove_event_handler(evt_class,dispatch_table[evt_class])
		elif evt_class is not None:
			robot.world.remove_event_handler(evt_class,monitor_generic)
		else:
			for k,v in dispatch_table.items():
				robot.world.remove_event_handler(k,v)
	except Exception:
		pass
#
# END OF EVENT MONITOR FUNCTIONS
#
# START THE SHOW!
#
cozmo.robot.Robot.drive_off_charger_on_connect = False
#
#uncomment the below line to load the viewer 
#cozmo.run_program(cozmo_unleashed, use_viewer=True)
#
# you may need to install a freeglut library, the cozmo SDK has documentation for this. If you don't have it comment the below line and uncomment the one above.
#cozmo.run_program(cozmo_unleashed, use_viewer=True, use_3d_viewer=True)
# which will give you remote control over Cozmo via WASD+QERF while the 3d window has focus
#
# below is just the program running without any camera view or 3d maps
cozmo.run_program(cozmo_unleashed)

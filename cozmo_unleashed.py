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
# You can improve this in several ways - better lights, custom printed large battery icon (and some fiddling with the docking routing)
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
global maxbatvoltage
global highbatvoltage
global lowbatvoltage
global batlightcounter
global use_scheduler
global camera
global foundcharger
global lightstate
global robotvolume
global debugging
global batcounter

# initialize needed variables
freeplay = 0
lightstate = 0
batcounter = 0
robot = cozmo.robot.Robot
msg = 'No status'
q = None # dependency on queue variable for messaging instead of printing to event-content directly
thread_running = False # starting thread for custom events

#
#============================
# CONFIGURABLE VARIABLES HERE
#============================
#
# BATTERY THRESHOLDS
#
# low battery voltage - when voltage drops below this Cozmo will start looking for his charger
# high battery voltage - when cozmo comes off your charger fully charge, this value will self-calibrate
# maxbatvoltage - the maximum battery level as recorded when cozmo is on charger but no longer charging
# tweak this to suit your cozmo
lowbatvoltage = 3.7
highbatvoltage= 4.14
maxbatvoltage = 4.8
#
# CUBE USAGE
#
# whether or not to activate the cubes (saves battery if you don't)
# I almost always leave this off, he will still stack them and mess around with them
# some games like "block guard dog" will not come up unless the blocks are active
use_cubes = 1
#
# COZMO VOLUME 
# what volume Cozmo should play sounds at, value between 0 and 1
robotvolume = 0.2
#
# SCHEDULER USAGE
#
# whether or not to use the schedule to define allowed "play times"
# this code is a bit rough, use at your own risk
use_scheduler = 0
# 
# DEBUGGING
# when disabled, clears the screen status updates
debugging = 0

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
	global cozmostate,freeplay,start_time,needslevel,scheduler_playokay,use_cubes, charger, batlightcounter, lowbatvoltage, highbatvoltage, maxbatvoltage, use_scheduler,msg,objmsg,facemsg,camera, foundcharger, tempfreeplay
	#robot.world.charger = None
	#charger = None
	foundcharger = 0
	robot.set_robot_volume(robotvolume)
	if use_cubes == 1:
		robot.enable_freeplay_cube_lights(enable=True)
	#robot.enable_device_imu(enable_raw=False, enable_user=True, enable_gyro=True)
	# set up some camera stuff
	robot.world.image_annotator.add_annotator('camera_info', camera_info)
	camera = robot.camera
	camera.enable_auto_exposure()
	robot.enable_facial_expression_estimation(enable=True)
	if use_cubes == 0:
		robot.world.disconnect_from_cubes()
	else:
		robot.world.connect_to_cubes()
	robot.enable_all_reaction_triggers(True)
	robot.enable_stop_on_cliff(True)
	q = None # dependency on queue variable for messaging instead of printing to event-content directly
	thread_running = False # starting thread for custom events
	robot.set_needs_levels(repair_value=1, energy_value=1, play_value=1)
	needslevel = 1
	tempfreeplay = 0
	lowbatcount=0
	batlightcounter=0
	cozmostate = 0
	#some custom objects that I printed out and use as virtual walls, if you don't have them don't worry about it, it won't affect the program
	# wall_obj1 = robot.world.define_custom_wall(CustomObjectTypes.CustomType01, CustomObjectMarkers.Circles2,  340, 120, 44, 44, True)
	# wall_obj2 = robot.world.define_custom_wall(CustomObjectTypes.CustomType02, CustomObjectMarkers.Circles4,  340, 120, 44, 44, True)
	# wall_obj3 = robot.world.define_custom_wall(CustomObjectTypes.CustomType03, CustomObjectMarkers.Circles5,  340, 120, 44, 44, True)
	# wall_obj4 = robot.world.define_custom_wall(CustomObjectTypes.CustomType04, CustomObjectMarkers.Triangles2,340, 120, 44, 44, True)
	# wall_obj5 = robot.world.define_custom_wall(CustomObjectTypes.CustomType05, CustomObjectMarkers.Triangles3,340, 120, 44, 44, True)
	# #wall_obj6 = robot.world.define_custom_wall(CustomObjectTypes.CustomType06, CustomObjectMarkers.Hexagons2, 120, 340, 44, 44, True)
	# wall_obj6 = robot.world.define_custom_wall(CustomObjectTypes.CustomType06, CustomObjectMarkers.Hexagons2, 44, 44, 44, 44, True)
	# wall_obj7 = robot.world.define_custom_wall(CustomObjectTypes.CustomType07, CustomObjectMarkers.Circles3,  120, 340, 44, 44, True)
	# wall_obj8 = robot.world.define_custom_wall(CustomObjectTypes.CustomType08, CustomObjectMarkers.Hexagons3, 120, 340, 44, 44, True)
	wall_obj1 = robot.world.define_custom_wall(CustomObjectTypes.CustomType01, CustomObjectMarkers.Hexagons2, 40, 40, 40, 40, True)
	# initialize event monitoring thread
	q = None
	monitor(robot, q)
	start_time = time.time()
	cozmostate=0
	robot_print_current_state('entering main loop')
# ENTERING STATE LOOP
	while True:
		#robot_backbackbatteryindicator()
		#robot_print_current_state('main loop checkpoint')
#

#State 1: on charger, charging
		if (robot.is_on_charger == 1) and (robot.is_charging == 1):
			if cozmostate != 1: # 1 is charging
				robot_print_current_state('switching to state 1')
				if cozmostate == 6:
					try:
						cozmostate = 1
						robot_reaction_chance(cozmo.anim.Triggers.SparkSuccess,1,True,False,False)
					except:
						pass
				cozmostate = 1
				start_time = time.time()
				foundcharger = 0
				if robot.is_freeplay_mode_active:
					######robot.enable_all_reaction_triggers(False)
					robot.stop_freeplay_behaviors()
				freeplay = 0
				if use_cubes == 1:
					robot.world.disconnect_from_cubes()
			lowbatcount=0
			cozmostate = 1
			robot_print_current_state('state 1 - charging')
			# once in a while make random snoring noises
			robot_check_sleep_snoring()
#
#State 2: on charger, fully charged
#
		if (robot.is_on_charger == 1) and (robot.is_charging == 0):
			cozmostate = 2
			robot_print_current_state('switching to state 2 - pausing 30 secs')
			time.sleep(30)
			if cozmostate != 2:  # 2 is fully charged
				maxbatvoltage = robot.battery_voltage
				robot_print_current_state('switching to state 2')
				cozmostate = 2
				lowbatcount=0
				foundcharger = 0
				if use_cubes == 1:
					robot.world.connect_to_cubes()
			robot_print_current_state('state 2 - charged')
			robot.set_needs_levels(repair_value=1, energy_value=1, play_value=1)
			# robot.drive_off_charger_contacts().wait_for_completed()
			# robot.drive_straight(distance_mm(100), speed_mmps(50)).wait_for_completed()
			robot_check_scheduler()
#
#State 3: not on charger, battery starting to get low
#
		# basic 'trigger guard' so Cozmo doesn't go to charger immediately if the voltage happens to dip below 3.7
		if (robot.battery_voltage <= lowbatvoltage) and (robot.is_on_charger == 0):
			lowbatcount += 1
			robot_set_needslevel()
			robot_print_current_state('state 3 - low battery threshold breach %s' % str(lowbatcount))
			# print("Event log      : %s" % str(msg))
			robot_reaction_chance(cozmo.anim.Triggers.CodeLabTakaTaka,1,False,False,False)
			time.sleep(0.5)
		# if we dip below the threshold three times we switch to state 5
		if lowbatcount > 2 and (robot.is_on_charger == 0) and cozmostate !=5:
			if use_cubes == 1:
				robot.world.disconnect_from_cubes()
			robot_set_needslevel()
			robot_print_current_state('state 3 - low battery - switching to state 5')
			cozmostate = 5
#			
#State 4: not on charger, good battery - freeplay active
#
		if (robot.battery_voltage > lowbatvoltage) and (robot.is_on_charger == 0) and cozmostate != 9 and cozmostate != 5 and cozmostate != 6 and cozmostate != 3 and lowbatcount < 3 and cozmostate != 99:
			if cozmostate != 4: # 4 is freeplay
				robot_print_current_state('freeplay - switching to state 4')
				cozmostate = 4
				if freeplay == 0:
					freeplay = 1
					start_time = time.time()
					try:
						robot.drive_wheels(40, 40, l_wheel_acc=50, r_wheel_acc=50, duration=1)
					except:
						robot_print_current_state('state 4 - failed to drive wheels')
					robot_reaction_chance(cozmo.anim.Triggers.OnSpeedtapGameCozmoWinHighIntensity,1,True,True,False)
					if use_cubes == 1:
						robot.world.connect_to_cubes()
					if not robot.is_freeplay_mode_active:
						#robot.enable_all_reaction_triggers(True)
						robot.start_freeplay_behaviors()
		if not robot.is_freeplay_mode_active and cozmostate == 4:
			robot_print_current_state('state 4 - re-enabling freeplay')
			freeplay = 1
			#robot.enable_all_reaction_triggers(True)
			robot.start_freeplay_behaviors()
			robot_set_needslevel()
		if cozmostate == 4:
			robot_check_randomreaction()
			time.sleep(0.5)

#
# state 5: battery low, looking for charger
#
		if cozmostate == 5 and tempfreeplay != 1:
			robot_print_current_state('switching to state 5')
			if robot.is_freeplay_mode_active:
				freeplay = 0
				robot.stop_freeplay_behaviors()
			#robot.enable_all_reaction_triggers(True)
			robot_locate_dock()
			# if cozmostate == 6:
				# pass
			# else:
				# cozmostate = 0

#
# state 6: battery low and we know where the charger is, moving to dock and docking
#
		if cozmostate == 6:
			robot_print_current_state('switching to state 6')
			if robot.is_freeplay_mode_active:
				#####robot.enable_all_reaction_triggers(False)
				robot.stop_freeplay_behaviors()
				freeplay = 0
			robot_print_current_state('initiating docking')
			robot.abort_all_actions(log_abort_messages=True)
			#robot.wait_for_all_actions_completed()
			freeplay = 0
			##robot_set_needslevel()
			if robot.world.charger:
				try:
					robot_print_current_state('state 6 - initiate docking')
					robot_start_docking()
				except:
					robot_print_current_state('switching to state 5')
					cozmostate = 5
					pass
			# else:
				# robot_print_current_state('switching to state 5')
				# cozmostate = 5
#
# state 9: we're on our side or are currently picked up
#
		if cozmostate == 9:
			robot_print_current_state('switching to state 9')
			robot_flash_backpacklights(4278190335)  # 4278190335 is red
			robot_reaction_chance(cozmo.anim.Triggers.CodeLabUnhappy,1,True,False,False)
			while cozmostate == 9:
				robot_print_current_state('state 9 - anger loop')
				robot_set_needslevel()
				if not robot.is_falling and not robot.is_picked_up:
					robot_print_current_state('state 9 reset - switching to 0')
					cozmostate = 0
					lightstate = 0
					break
				if robot.is_freeplay_mode_active:
					#robot.enable_all_reaction_triggers(True)
					robot.stop_freeplay_behaviors()
					freeplay = 0
				robot.abort_all_actions(log_abort_messages=True)
				robot.clear_idle_animation()
				robot.wait_for_all_actions_completed()
				robot_reaction_chance(cozmo.anim.Triggers.AskToBeRightedLeft,1,False,False,False)
				robot_print_current_state('picked annoyed response 1')
				time.sleep(0.5)
				if not robot.is_falling and not robot.is_picked_up:
					robot_print_current_state('state reset - switching to 0')
					cozmostate = 0
					lightstate = 0
					break
				robot_reaction_chance(cozmo.anim.Triggers.TurtleRoll,1,False,False,False)
				robot_print_current_state('picked annoyed response 2')
				time.sleep(0.5)
				if not robot.is_falling and not robot.is_picked_up:
					robot_print_current_state('state reset - switching to 0')
					cozmostate = 0
					lightstate = 0
					break
				robot_reaction_chance(cozmo.anim.Triggers.CodeLabUnhappy,1,True,False,False)
				robot_print_current_state('picked annoyed response 3')
				time.sleep(0.5)
				robot_print_current_state('state 9 - loop complete')

#
# state 0: recovery state
#		
		if cozmostate == 0:
			robot_print_current_state('state 0')
			robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,True,True,True)
			robot.set_all_backpack_lights(cozmo.lights.white_light)
			lightstate = 0
			time.sleep(0.5)

#			
# state 99: animation is playing (not an official state)
#

#			
# we have looped through the states
#
		#robot_set_needslevel()
		#robot_reaction_chance(cozmo.anim.Triggers.CodeLabChatty,1,True,True,True)
		#msg = 'state loop complete'
		#robot_check_randomreaction()
		#robot_print_current_state('cozmo_unleashed state program loop complete')
		time.sleep(0.5)
#
#
# END OF STATE LOOP
# 
	##robot_set_needslevel()
	robot_reaction_chance(cozmo.anim.Triggers.CodeLabTakaTaka,1,True,True,False)
	robot_print_current_state('exiting main loop - how did we get here?')

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

def robot_backbackbatteryindicator():
	global robot,highbatvoltage,lowbatvoltage,maxbatvoltage,lightstate,batlightcounter
	batmultiplier = ((highbatvoltage - lowbatvoltage)/3)+0.1
	chargebatmultiplier = ((maxbatvoltage - lowbatvoltage)/3)+0.1
	critbatmultiplier = ((lowbatvoltage - 3.5)/3)
	robotvoltage=(robot.battery_voltage)
	if not lightstate:
		lightstate = 0
	oldlightstate = lightstate
	if robotvoltage > (highbatvoltage-batmultiplier) and cozmostate==4:
		# bottom two lights on, third light blinking
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=1 and lightstate !=2:
			lightstate = 1
			color1=cozmo.lights.Color(int_color=16711935, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1)
			light2=cozmo.lights.Light(on_color=color1)
			light3=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=1000)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	elif robotvoltage > (highbatvoltage-(batmultiplier*1.5)) and robotvoltage <= (highbatvoltage-batmultiplier) and cozmostate==4:
		#bottom one light on, second light blinking
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=2 and lightstate !=3:
			lightstate = 2
			color1=cozmo.lights.Color(int_color=16711935, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1)
			light2=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=1000)
			light3=cozmo.lights.Light(on_color=color2)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	elif robotvoltage > (highbatvoltage-(batmultiplier*2.5)) and robotvoltage <= (highbatvoltage-(batmultiplier*1.5)) and cozmostate==4:
		# # bottom one light blinking
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=3:
			lightstate = 3
			color1=cozmo.lights.Color(int_color=16711935, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=1000)
			light2=cozmo.lights.Light(on_color=color2)
			light3=cozmo.lights.Light(on_color=color2)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	elif robotvoltage >= lowbatvoltage and cozmostate==4:
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=4:
			lightstate = 4
			color1=cozmo.lights.Color(int_color=16711935, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=500, off_period_ms=500, transition_on_period_ms=500, transition_off_period_ms=500)
			light2=cozmo.lights.Light(on_color=color2)
			light3=cozmo.lights.Light(on_color=color2)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	#robot_set_backpacklights(65535)  # 65535 is blue
	elif robotvoltage >= (maxbatvoltage-(chargebatmultiplier/2.5)) and robotvoltage <= (maxbatvoltage-(chargebatmultiplier/3.5)) and cozmostate==1:
		# # bottom one light blinking
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=7 and lightstate !=6 and lightstate !=5:
			lightstate = 7
			color1=cozmo.lights.Color(int_color=65535, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=1000)
			light2=cozmo.lights.Light(on_color=color2)
			light3=cozmo.lights.Light(on_color=color2)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	elif robotvoltage >= (maxbatvoltage-(chargebatmultiplier/1.0)) and robotvoltage <= (maxbatvoltage-chargebatmultiplier/2.5) and cozmostate==1:
		#bottom one light on, second light blinking
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=6 and lightstate !=5:
			lightstate = 6
			color1=cozmo.lights.Color(int_color=65535, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1)
			light2=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=1000)
			light3=cozmo.lights.Light(on_color=color2)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	elif robotvoltage >= maxbatvoltage and cozmostate==1:
		# bottom two lights on, third light blinking
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=5:
			lightstate = 5
			color1=cozmo.lights.Color(int_color=65535, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1)
			light2=cozmo.lights.Light(on_color=color1)
			light3=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=1000)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	# elif robotvoltage >= maxbatvoltage and cozmostate==1:
		# batlightcounter +=1
		# if batlightcounter > 5 and lightstate !=8:
			# lightstate = 8
			# color1=cozmo.lights.Color(int_color=65535, rgb=None, name=None)
			# color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			# light1=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=500, off_period_ms=500, transition_on_period_ms=500, transition_off_period_ms=500)
			# light2=cozmo.lights.Light(on_color=color2)
			# light3=cozmo.lights.Light(on_color=color2)
			# robot.set_backpack_lights(None, light3, light2, light1, None)
			# batlightcounter = 0
		# pass
	#robot_set_backpacklights(4278190335)  # 4278190335 is red
	elif robotvoltage >= (lowbatvoltage-critbatmultiplier) and cozmostate==5:
		# bottom two lights on, third light blinking
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=9:
			lightstate = 9
			color1=cozmo.lights.Color(int_color=4278190335, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1)
			light2=cozmo.lights.Light(on_color=color1)
			light3=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=1000)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	elif robotvoltage >= (lowbatvoltage-(critbatmultiplier*1.5)) and robotvoltage <= (lowbatvoltage-critbatmultiplier) and cozmostate==5:
		#bottom one light on, second light blinking
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=10  and lightstate !=9:
			lightstate = 10
			color1=cozmo.lights.Color(int_color=4278190335, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1)
			light2=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=1000)
			light3=cozmo.lights.Light(on_color=color2)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	elif robotvoltage >= (lowbatvoltage-(critbatmultiplier*2.5)) and robotvoltage <= (lowbatvoltage-(critbatmultiplier*1.5)) and cozmostate==5:
		# # bottom one light blinking
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=11  and lightstate !=10:
			lightstate = 11
			color1=cozmo.lights.Color(int_color=4278190335, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=1000)
			light2=cozmo.lights.Light(on_color=color2)
			light3=cozmo.lights.Light(on_color=color2)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	elif robotvoltage >= lowbatvoltage and cozmostate==5:
		batlightcounter +=1
		if batlightcounter > 5 and lightstate !=12:
			lightstate = 12
			color1=cozmo.lights.Color(int_color=4278190335, rgb=None, name=None)
			color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
			light1=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=500, off_period_ms=500, transition_on_period_ms=500, transition_off_period_ms=500)
			light2=cozmo.lights.Light(on_color=color2)
			light3=cozmo.lights.Light(on_color=color2)
			robot.set_backpack_lights(None, light3, light2, light1, None)
			batlightcounter = 0
		pass
	if lightstate==0 or lightstate==99:
		lightstate=99
		if robot.is_on_charger:
			robot_set_backpacklights(65535)  # 16711935 is green
		else:
			if robot.battery_voltage > lowbatvoltage:
				robot_set_backpacklights(16711935)  # 65535 is blue
			else :
				robot_set_backpacklights(4278190335)  # 4278190335 is red
		
	
def robot_set_needslevel():
	global robot, needslevel, msg
	needslevel = 1 - (4.05 - robot.battery_voltage)
	if needslevel < 0.1:
		needslevel = 0.1
	if needslevel > 1:
		needslevel = 1
	# i = random.randint(1, 1000)
	# if i >= 990:
	#robot_print_current_state('updating needs levels')
	robot.set_needs_levels(repair_value=needslevel, energy_value=needslevel, play_value=needslevel)

def robot_check_sleep_snoring():
	global robot
	i = random.randint(1, 1000)
	if i >= 997:
		robot_print_current_state('check complete - snore')
		#robot.play_anim_trigger(Sleeping).wait_for_completed()
		robot_reaction_chance(cozmo.anim.Triggers.Sleeping,1,True,False,False)
	else:
		#robot_print_current_state('check complete - no snore')
		time.sleep(0.5)

def robot_check_randomreaction():
	global robot,cozmostate,freeplay
	i = random.randint(1, 1000)
	#if i >= 980 and not robot.is_carrying_block and not robot.is_picking_or_placing and not robot.is_pathing and not robot.is_behavior_running and cozmostate==4:
	if i >= 950 and not robot.is_carrying_block and not robot.is_picking_or_placing and not robot.is_pathing and cozmostate==4:
		oldcozmostate=cozmostate
		cozmostate=99
		#random action!
		robot_print_current_state('random animation starting')
		if robot.is_freeplay_mode_active:
			#robot.enable_all_reaction_triggers(True)
			robot.stop_freeplay_behaviors()
		robot.abort_all_actions(log_abort_messages=True)
		robot.clear_idle_animation()
		robot.wait_for_all_actions_completed()
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
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'MeetCozmo' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'list' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'List' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'Severe' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'TakaTaka' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'Test' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'Loop' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'Sleep' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'Request' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'Singing' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'Drone' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
			if 'SoundOnly' in trigger:
				trigger = 'cozmo.anim.Triggers.SparkSuccess'
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
			#robot.enable_all_reaction_triggers(True)
			robot.start_freeplay_behaviors()
		if cozmostate==6:
			cozmostate==6
		else:
			cozmostate=oldcozmostate
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

def robot_reaction_chance(animation,chance,ignorebody,ignorehead,ignorelift):
	global robot, msg, freeplay,cozmostate
	i = random.randint(1, 100)
	if i >= chance and not robot.is_behavior_running:
		robot_print_current_state('starting animation')
		oldcozmostate=cozmostate
		cozmostate=99
		# oldfreeplay = 0
		# if freeplay == 1:
			# if robot.is_freeplay_mode_active:
				# robot_print_current_state('disabling freeplay')
				# #robot.enable_all_reaction_triggers(True)
				# robot.stop_freeplay_behaviors()
			# oldfreeplay = 1
			# freeplay = 0
		robot.stop_freeplay_behaviors()
		robot.abort_all_actions(log_abort_messages=True)
		robot_print_current_state('action queue aborted')
		robot.clear_idle_animation()
		robot.wait_for_all_actions_completed()
		try:
			robot.play_anim_trigger(animation, ignore_body_track=ignorebody, ignore_head_track=ignorehead, ignore_lift_track=ignorelift).wait_for_completed()
			#print("reaction %s" %str(animation)," executed")
			msg = ("reaction %s" %str(animation)," executed")
			robot_print_current_state('animation completed')
		except:
			robot_print_current_state('animation failed')
			#print("reaction %s" %str(animation)," aborted")
			
		#robot.wait_for_all_actions_completed()
		try:
			robot.set_head_angle(degrees(0)).wait_for_completed()
		except:
			robot_print_current_state('head angle reset failed')
			#print("reaction %s" %str(animation)," aborted")
		#robot.wait_for_all_actions_completed()
		try:
			robot.move_lift(-3)
		except:
			robot_print_current_state('lift move down failed')
			#print("reaction %s" %str(animation)," aborted")
		# if oldfreeplay == 1:
			# oldfreeplay = 0
			# freeplay = 1
			# robot_print_current_state('re-enabling freeplay')
			# if not robot.is_freeplay_mode_active:
				# #robot.enable_all_reaction_triggers(True)
				# robot.start_freeplay_behaviors()
		if cozmostate == 6:
			cozmostate =6
		else:
			cozmostate=oldcozmostate
	else:
		time.sleep(0.5)
		robot_print_current_state('animation check - no winner')

def robot_locate_dock():
	global cozmostate,freeplay,start_time,needslevel,scheduler_playokay,use_cubes, charger, lowbatvoltage, use_scheduler,msg, camera, foundcharger, tempfreeplay
	#back off from whatever we were doing
	#robot_set_backpacklights(4278190335)  # 4278190335 is red
	if robot.is_freeplay_mode_active:
		robot_print_current_state('disabling freeplay')
		robot.stop_freeplay_behaviors()
	#robot.enable_all_reaction_triggers(True)
	robot.abort_all_actions(log_abort_messages=True)
	robot_print_current_state('starting locate dock sequence')
	robot.clear_idle_animation()
	#robot.wait_for_all_actions_completed()
	if use_cubes==1:
		robot.world.disconnect_from_cubes()
	freeplay = 0
	robot_reaction_chance(cozmo.anim.Triggers.NeedsMildLowEnergyRequest,1,False,False,False)
	try:
		robot.drive_straight(distance_mm(-30), speed_mmps(50)).wait_for_completed()
	except:
		robot_print_current_state('drive straight failed')
	##robot_set_needslevel()
	robot_print_current_state('finding charger')
	# charger location search
	if not robot.world.charger and cozmostate != 1 and cozmostate != 2 and cozmostate !=6:
		charger = None
		robot.world.charger = None
		cozmostate=5
	# see if we already know where the charger is
	if robot.world.charger and cozmostate != 1 and cozmostate != 2 and cozmostate !=6:
		if robot.world.charger.pose.is_comparable(robot.pose):
			charger = robot.world.charger
			#we know where the charger is
			robot_print_current_state('finding charger, charger position known')
			cozmostate = 6
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
	if not charger and cozmostate != 1 and cozmostate != 2 and cozmostate !=6:
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
	robot_print_current_state('go to object complete')
	action = robot.go_to_pose(robot.world.charger.pose)
	action.wait_for_completed()
	robot_print_current_state('go to pose complete')
	robot.drive_straight(distance_mm(-50), speed_mmps(50)).wait_for_completed()
	robot_print_current_state('drove back a little bit')
	if not robot.world.charger.pose.is_comparable(robot.pose):
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
		robot_print_current_state('I should be in front of the charger')
		robot.set_head_light(False)
		time.sleep(0.5)
		robot.set_head_light(True)
		time.sleep(0.5)
		robot.set_head_light(False)
		if not robot.world.charger:
			charger = None
			robot.world.charger = None
			cozmostate=5
			robot.play_anim_trigger(cozmo.anim.Triggers.ReactToPokeReaction, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=True).wait_for_completed()
			break
			# # we can't see it. Remove charger from navigation map and quit this loop.
			# robot.world.charger = None
			# charger = None
			
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
		robot.turn_in_place(degrees(94)).wait_for_completed()
		robot.turn_in_place(degrees(94)).wait_for_completed()
		time.sleep(0.5)
		robot_reaction_chance(cozmo.anim.Triggers.CubePounceFake,1,True,False,False)
		robot.drive_straight(distance_mm(-145), speed_mmps(150)).wait_for_completed()
		time.sleep(0.5)
		# check if we're now docked
		if robot.is_on_charger:
			# Yes! we're docked!
			#cozmostate = 1
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
				robot.turn_in_place(degrees(94)).wait_for_completed()
			except:
				pass
			try:
				robot.set_head_angle(degrees(0)).wait_for_completed()
			except:
				pass
		time.sleep(0.5)
		dockloop+=1
	charger= None
	robot.world.charger=None
	cozmostate=5
	# express frustration
	try:
		robot.drive_straight(distance_mm(50), speed_mmps(50)).wait_for_completed()
	except:
		pass
	try:
	#
	#
		# a= random.randrange(=3, 17, 8)
		# t= random.randrange(1, 2, 1)
		# if random.choice((True, False)):
				# rx=50
			# else:
				# rx=-50
			# ry=-rx
			# robot_print_current_state('looking for charger, rotating')
			# try:
				# robot.set_head_light(False)
				# time.sleep(0.2)
				# robot.set_head_light(True)
				# time.sleep(0.2)
				# robot.set_head_light(False)
				# robot.drive_wheels(rx, ry, l_wheel_acc=a, r_wheel_acc=a, duration=t)
				# time.sleep(0.5)
			# except:
				# pass
	
	
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
			#robot_set_backpacklights(16711935) # green
			if use_cubes==1:
				robot.world.connect_to_cubes()
			if not robot.is_freeplay_mode_active:
				robot_print_current_state('freeplay enabled')
				#robot.enable_all_reaction_triggers(True)
				robot.start_freeplay_behaviors()
		if cozmostate != 5:
			break
		robot_print_current_state('charger not found, falling back to freeplay')
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
		#robot.enable_all_reaction_triggers(True)
		robot.stop_freeplay_behaviors()
	if use_cubes==1:
		robot.world.disconnect_from_cubes()
	#robot_set_backpacklights(4278190335) # red
	freeplay = 0
	cozmostate = 5
	#os.system('cls' if os.name == 'nt' else 'clear')
	robot_print_current_state('temporary freeplay ended')
	time.sleep(1)
						
def robot_drive_random_pattern():
	global cozmostate,freeplay,start_time,needslevel,scheduler_playokay,use_cubes, charger, lowbatvoltage, use_scheduler,msg, camera, foundcharger
	loops=5
	while loops>0 and cozmostate == 5:
		if robot.world.charger and robot.world.charger.pose.is_comparable(robot.pose):
			loops=0
			charger = robot.world.charger
			robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,False,False,False)
			robot_print_current_state('found charger, breaking loop')
			cozmostate = 6
			foundcharger = 1
			break
		if cozmostate == 6 or cozmostate ==1 or cozmostate == 2:
			robot_print_current_state('breaking out of drive loop')
			break
		# drive to a random point and orientation
		counter=0
		while counter < 1 and cozmostate ==5 and cozmostate !=6:
			if cozmostate == 6 or cozmostate ==1 or cozmostate == 2:
				robot_print_current_state('breaking out of drive loop')
				break
			if random.choice((True, False)):
				x=150
			else:
				x=-150
			if random.choice((True, False)):
				y=150
			else:
				y=-150
			z= random.randrange(-40, 41, 80)
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
			if cozmostate == 6 or cozmostate ==1 or cozmostate == 2:
				break
			if robot.world.charger and robot.world.charger.pose.is_comparable(robot.pose):
				loops=0
				charger = robot.world.charger
				cozmostate = 6
				foundcharger = 1
				robot_print_current_state('found charger, breaking')
				robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,False,False,False)
				break
			# else:
			robot_check_randomreaction()
			counter+=1
		if cozmostate == 6 or cozmostate ==1 or cozmostate == 2:
			break
		robot_reaction_chance(cozmo.anim.Triggers.CodeLabChatty,1,False,False,False)
		# turn around for a bit
		time.sleep(0.5)
		counter=0
		
		oldcozmostate = cozmostate
		cozmostate = 99
		robot_print_current_state('start lookaround behavior')
		look_around = robot.start_behavior(cozmo.behavior.BehaviorTypes.LookAroundInPlace)
		
		#look_around = robot.start_behavior(cozmo.behavior.BehaviorTypes.LookAroundInPlace)
		try:
			custom_objects = robot.world.wait_until_observe_num_objects(num=1, object_type = CustomObject, timeout=15)
			print("Found object: %s" % str(CustomObjectTypes.CustomType01))
		except asyncio.TimeoutError:
			print("timeout")
		finally:
			look_around.stop()
		if len(custom_objects) > 0:
			found_object = custom_objects[0]
			if str(found_object.object_type) == "CustomObjectTypes.CustomType01":
				action = robot.go_to_pose(pose=found_object.pose)
				action.wait_for_completed()
				robot.set_head_angle(degrees(20)).wait_for_completed()
				robot.drive_straight(distance_mm(-80), speed_mmps(50)).wait_for_completed()
				robot.drive_straight(distance_mm(-80), speed_mmps(50)).wait_for_completed()
			else:
				print("no object to drive to")
				pass
		
				# try:
			# charger = robot.world.wait_for_observed_charger(timeout=8)
			# #print("Found charger: %s" % charger)
			# robot_print_current_state('found charger, breaking')
			# cozmostate=6
		# except asyncio.TimeoutError:
			# #print("Didn't see the charger")
			# robot_print_current_state('charger not found')
			# cozmostate=5
		# finally:
			# # whether we find it or not, we want to stop the behavior
			# #robot_print_current_state('lookaround behavior ending')
			# look_around.stop()
		#cozmostate = oldcozmostate
		if cozmostate == 6 or cozmostate ==1 or cozmostate == 2:
			break
		robot_reaction_chance(cozmo.anim.Triggers.CodeLabChatty,1,False,False,False)
		robot_print_current_state('ended lookaround behavior')
		# while counter <2 and cozmostate == 5:
			# a= random.randrange(8, 17, 8)
			# t= random.randrange(2, 4, 1)
			# if random.choice((True, False)):
				# rx=50
			# else:
				# rx=-50
			# ry=-rx
			# robot_print_current_state('looking for charger, rotating')
			# try:
				# robot.set_head_light(False)
				# time.sleep(0.2)
				# robot.set_head_light(True)
				# time.sleep(0.2)
				# robot.set_head_light(False)
				# robot.drive_wheels(rx, ry, l_wheel_acc=a, r_wheel_acc=a, duration=t)
				# time.sleep(0.5)
			# except:
				# pass
		if cozmostate == 6:
			break
		if robot.world.charger and robot.world.charger.pose.is_comparable(robot.pose):
			loops=0
			charger = robot.world.charger
			robot_print_current_state('found charger')
			foundcharger = 1
			robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,False,False,False)
			break
		# else:
		robot_check_randomreaction()
			# counter+=1
		
		if robot.world.charger and robot.world.charger.pose.is_comparable(robot.pose):
			loops=0
			charger = robot.world.charger
			cozmostate = 6
			foundcharger = 1
			robot_print_current_state('found charger')
			robot_reaction_chance(cozmo.anim.Triggers.CodeLabSurprise,1,False,False,False)
			break
		#robot_set_needslevel()
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
	global robot,cozmostate,freeplay,msg,camera,objmsg,facemsg
	def __init__(self, thread_id, name, _q):
		threading.Thread.__init__(self)
		self.threadID = thread_id
		self.name = name
		self.q = _q

# main thread
	def run(self):
		global robot,cozmostate,freeplay,msg,camera,highbatvoltage,lowbatvoltage,lightstate
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

			#robot_backbackbatteryindicator()

			if robot.is_picked_up:
				delay = 0
				if not is_picked_up:
					is_picked_up = True
					robot_flash_backpacklights(4278190335)  # 4278190335 is red
					cozmostate = 9
					robot_print_current_state('switching to state 9 - picked up')
					lightstate=0
			elif is_picked_up and delay > 9:
				cozmostate = 0
				lightstate=0
				is_picked_up = False
				robot_print_current_state('no longer picked up - state 0')
			elif delay <= 9:
				delay += 1
				
# event monitor: robot is carrying a block

			# if robot.is_carrying_block:
				# if not is_carrying_block:
					# is_carrying_block = True
					# robot_print_current_state('cozmo.robot.Robot.is_carrying_block: True')
			# elif not robot.is_carrying_block:
				# if is_carrying_block:
					# is_carrying_block = False
					# robot_print_current_state('cozmo.robot.Robot.is_carrying_block: False')

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

			# if robot.is_falling:
				# if not is_falling:
					# is_falling = True
					# robot.stop_all_motors()
						
					# cozmostate = 9
					# robot_print_current_state('Switching to state 9 - Falling!')
					# lightstate=0
			# elif not robot.is_falling:
				# if is_falling:
					# is_falling = False
					# cozmostate = 0
					# lightstate=0
					# robot_print_current_state('no longer falling switching to state 0')

# event monitor: robot moves onto charger

			if robot.is_on_charger:
				if not is_on_charger:
					is_on_charger = True
					#freeplay = 0
					cozmostate = 1
					# if robot.is_freeplay_mode_active:
						# #robot.enable_all_reaction_triggers(True)
						# robot.stop_freeplay_behaviors()
					# robot.abort_all_actions(log_abort_messages=True)
					# robot.wait_for_all_actions_completed()
					# robot.clear_idle_animation()
					# robot.stop_all_motors()
					msg = 'cozmo.robot.Robot.is_on_charger: True'
					color1=cozmo.lights.Color(int_color=65535, rgb=None, name=None)
					light1=cozmo.lights.Light(on_color=color1)
					light2=cozmo.lights.Light(on_color=color1)
					light3=cozmo.lights.Light(on_color=color1)
					robot.set_backpack_lights(None, light3, light2, light1, None)
					# robot_set_backpacklights(65535)  # 65535 is blue
					lightstate = 0
					# #robot.play_anim_trigger(cozmo.anim.Triggers.Sleeping, loop_count=1, in_parallel=True, num_retries=0, ignore_body_track=True, ignore_head_track=False, ignore_lift_track=True).wait_for_completed()
					# try:
						# robot.play_anim_trigger(cozmo.anim.Triggers.GoToSleepGetIn).wait_for_completed()
					# except:
						# pass
					#robot_set_backpacklights(65535) # blue
					# if cozmostate==6:
						# try:
							# #robot.play_anim("anim_sparking_success_02").wait_for_completed()
							# robot_reaction_chance(cozmo.anim.Triggers.SparkSuccess,1,True,False,False)
						# except:
							# pass
						# try:
							# robot.set_head_angle(degrees(0)).wait_for_completed()
						# except:
							# pass
						# robot_print_current_state('docked')
					# try:
						# #robot.play_anim("anim_gotosleep_getin_01").wait_for_completed()
						# robot_reaction_chance(cozmo.anim.Triggers.GoToSleepGetIn,1,True,False,False)
					# except:
						# pass
					# try:
						# robot_reaction_chance(cozmo.anim.Triggers.CodeLabSleep,1,True,False,False)
						# #robot.play_anim("anim_gotosleep_sleeping_01").wait_for_completed()
					# except:
						# pass
					
					#robot.play_anim_trigger(cozmo.anim.Triggers.StartSleeping, loop_count=1, in_parallel=True, num_retries=0, ignore_body_track=True, ignore_head_track=False, ignore_lift_track=True).wait_for_completed()
					if robot.is_charging:
						cozmostate = 1
						robot_print_current_state('switching to state 1 - moved onto charger')
					else:
						cozmostate = 2
						maxbatvoltage = robot.battery_voltage
						robot_print_current_state('not charging')
					#print(msg)
			elif not robot.is_on_charger:
				if is_on_charger:
					#robot_set_backpacklights(16711935)  # 16711935 is green
					color1=cozmo.lights.Color(int_color=16711935, rgb=None, name=None)
					light1=cozmo.lights.Light(on_color=color1)
					light2=cozmo.lights.Light(on_color=color1)
					light3=cozmo.lights.Light(on_color=color1)
					is_on_charger = False
					cozmostate = 0
					msg = 'cozmo.robot.Robot.is_on_charger: False'
					robot_print_current_state('switching to state 0 - moved off charger')
					#print(msg)

# event monitor: robot has detected cliff

			# if robot.is_cliff_detected and not robot.is_falling and not robot.is_picked_up:
				# if not is_cliff_detected:
					# robot.stop_all_motors()
					# is_cliff_detected = True
					# wasinfreeplay = 0
					# msg = 'cozmo.robot.Robot.is_cliff_detected: True'
					# robot_print_current_state('cliff detected')
					# #print(msg)
					# if freeplay == 1:
						# freeplay = 0
						# wasinfreeplay = 1
						# if robot.is_freeplay_mode_active:
							# ##robot.enable_all_reaction_triggers(True)
							# robot.stop_freeplay_behaviors()
						# #robot.wait_for_all_actions_completed()
					# robot.abort_all_actions(log_abort_messages=True)
					# robot.clear_idle_animation()
					# try:
						# robot.drive_wheels(-40, -40, l_wheel_acc=30, r_wheel_acc=30, duration=1.5)
					# except:
						# pass
					# try:
						# robot.drive_wheels(-40, -40, l_wheel_acc=30, r_wheel_acc=30, duration=1.5)
					# except:
						# pass
					# is_cliff_detected = False
					# msg = 'cozmo.robot.Robot.is_cliff_detected: False'
					# robot_print_current_state('cliff no longer detected')
					# #print(msg)
			# elif not robot.is_cliff_detected:
				# if is_cliff_detected:
					# is_cliff_detected = False
					# if wasinfreeplay == 1:
						# freeplay = 1
						# wasinfreeplay = 0
						# if robot.is_freeplay_mode_active:
							# ##robot.enable_all_reaction_triggers(True)
							# robot.start_freeplay_behaviors()

# event monitor: robot is picking or placing something
			# if robot.is_picking_or_placing:
				# if not is_picking_or_placing:
					# is_picking_or_placing = True
					# msg = 'cozmo.robot.Robot.is_picking_or_placing: True'
					# #print(msg)
					# robot_print_current_state('Robot.is_picking_or_placing: True')
			# elif not robot.is_picking_or_placing:
				# if is_picking_or_placing:
					# is_picking_or_placing = False
					# msg = 'cozmo.robot.Robot.is_picking_or_placing: False'
					# robot_print_current_state('Robot.is_picking_or_placing: False')
					# #print(msg)		
				
# event monitor: robot is pathing (traveling to a target)
			# if robot.is_pathing:
				# if not is_pathing:
					# is_pathing = True
					# msg = 'cozmo.robot.Robot.is_pathing: True'
					# #print(msg)
					# robot_print_current_state('Robot.is_pathing: True')
			# elif not robot.is_pathing:
				# if is_pathing:
					# is_pathing = False
					# msg = 'cozmo.robot.Robot.is_pathing: False'
					# robot_print_current_state('Robot.is_pathing: False')
					# #print(msg)	
				
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
	global robot,cozmostate,freeplay,msg,camera,objmsg,facemsg
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

#
# event monitor: robot is experiencing unexpected movement
#
def monitor_EvtUnexpectedMovement(evt, **kwargs):
	global robot,cozmostate,freeplay,msg,camera
	msg = kwargs
	robot_print_current_state('unexpected movement')
	#print(msg)
	if  cozmostate != 3 and cozmostate !=9 and cozmostate !=6:
		robot_print_current_state('unexpected behavior during action; aborting')
		#print("unexpected behavior during action; aborting")
		robot.abort_all_actions(log_abort_messages=True)
		robot.wait_for_all_actions_completed()
		#print("unexpected behavior during action; aborting")
		robot_print_current_state('unexpected behavior during action; aborting')
		

#
# event monitor: an object was tapped
#
def monitor_EvtObjectTapped(evt, *, obj, tap_count, tap_duration, tap_intensity, **kwargs):
	msg = print_prefix(evt)
	msg += print_object(obj)
	msg += ' count=' + str(tap_count) + ' duration=' + str(tap_duration) + ' intensity=' + str(tap_intensity)
	robot_print_current_state('object tapped')
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
	global cozmostate,freeplay,start_time,needslevel,scheduler_playokay,use_cubes, charger, lowbatvoltage, use_scheduler,msg, camera, foundcharger,bhvmsg,facemsg,objmsg
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

dispatch_table = {
  
  cozmo.objects.EvtObjectTapped        : monitor_EvtObjectTapped,
  cozmo.objects.EvtObjectMovingStarted : monitor_EvtObjectMovingStarted,
  cozmo.objects.EvtObjectMovingStopped : monitor_EvtObjectMovingStopped,
  cozmo.objects.EvtObjectAppeared      : monitor_EvtObjectAppeared,
  cozmo.faces.EvtFaceAppeared          : monitor_face,
  cozmo.faces.EvtFaceDisappeared       : monitor_face,
  cozmo.robot.EvtUnexpectedMovement    : monitor_EvtUnexpectedMovement,

}


excluded_events = {	# Occur too frequently to monitor by default
	
	 cozmo.behavior.EvtBehaviorRequested,
	 cozmo.objects.EvtObjectDisappeared,
	 cozmo.faces.EvtFaceObserved,
	 cozmo.objects.EvtObjectObserved
	 
	 
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
		
def robot_print_current_state(currentstate):
	global robot,needslevel,start_time,cozmostate,msg,highbatvoltage,maxbatvoltage,objmsg,facemsg,bhvmsg,lightstate,batlightcounter,debugging, batcounter
	if not batcounter:
		batcounter = 0
	if batcounter > 2:
		robot_backbackbatteryindicator()
		batcounter = 0
	batcounter += 1
	robot_set_needslevel()
	if debugging==1:
		print("State: %s" % str(currentstate),"battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2)," runtime %s" % round(((time.time() - start_time)/60),2)," internal state %s" % cozmostate," last message: %s" % str(msg))
	else:
		os.system('cls' if os.name == 'nt' else 'clear')
		print("State          : %s" % str(currentstate))
		print("Internal state : %s" % str(cozmostate))
		print("Battery        : %s" % (str(round(robot.battery_voltage, 2))))
		print("Energy         : %s" % (round(needslevel, 2)))
		print("Runtime        : %s" % (round(((time.time() - start_time)/60),2)))
		print("running behav  : %s" % (str(robot.is_behavior_running)))
		print("animating      : %s" % (str(robot.is_animating)))
		print("Event log      : %s" % str(msg))
		#print("cozmo sees     : %s"  % str(robot.world.connected_light_cubes))
		#print("wheelie        : %s" % str(robot.PopAWheelie))
		#print("Cubes connected: %s" % robot.world.World.active_behavior.connected_light_cubes)
		#print("Behavior       : %s" % str(cozmo.behavior.Behavior))
		#print("Max Battery    : %s" % str(round(maxbatvoltage, 2)))
		#print("Max off charger: %s" % str(round(highbatvoltage, 2))) 
		#print("idle anim      : %s" % str(robot.is_animating_idle))
		#print("actions        : %s" % str(robot.has_in_progress_actions))
		print("Lightstate     : %s" % str(lightstate))
		# print("Object log     : %s" %objmsg)
		# print("Face log       : %s" %facemsg)
		# print("Behavior log   : %s" %bhvmsg)
	
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

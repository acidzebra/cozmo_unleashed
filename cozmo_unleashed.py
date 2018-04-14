#!/usr/bin/env python3
import sys, os, datetime, random, time, math, re, threading
import asyncio, cozmo, cozmo.objects, cozmo.util
import event_monitor
from cozmo.util import degrees, distance_mm, speed_mmps, Pose
from cozmo.objects import CustomObject, CustomObjectMarkers, CustomObjectTypes
from PIL import ImageDraw, ImageFont
import numpy as np
global robot
#define globals
global freeplay
freeplay=0
robot = cozmo.robot.Robot

@cozmo.annotate.annotator
def camera_info(image, scale, annotator=None, world=None, **kw):
	d = ImageDraw.Draw(image)
	bounds = [3, 0, image.width, image.height]

	camera = world.robot.camera
	text_to_display = 'Exposure: %s ms\n' % camera.exposure_ms
	text_to_display += 'Gain: %.3f\n' % camera.gain
	text = cozmo.annotate.ImageText(text_to_display,position=cozmo.annotate.TOP_LEFT,line_spacing=2,color="white",outline_color="black", full_outline=True)
	text.render(d, bounds)

# three types of functions are defined
# robot_state_XXX 			- the current state the robot is in
# robot_status_XXX_check 	- check for a particular thing
# robot_action_XXX 			- do a thing

# MAIN PROGRAM LOOP
def cozmo_unleashed(robot: cozmo.robot.Robot):
	# CONFIGURABLE VARIABLES HERE
	# CHANGE TO YOUR LIKING
	#
	# scheduler; allowed play times in 24H notation 
	# from 7pm on weekdays

	usescheduler = 0
	weekdaystartplay = 19
	# to 11pm on weekdays
	weekdaystopplay  = 23
	# from 7am on weekends
	weekendstartplay = 7
	# to 11pm on weekends
	weekendstopplay  = 23
	# scheduler - when battery is charged this represents the chance cozmo will get off his charger to play
	# chance is defined as a number between 1-99 with a higher number representing a lesser chance
	playchance = 80
	#
	# low battery voltage - the point where Cozmo will start looking for his charger
	#
	lowbatvoltage = 3.7
	robot.set_robot_volume(0.2)
	# 
	#cozmo will get less happy as his battery decreases. The mood modifier can be used to adjust this
	# suggested range 3.5-4.5, a lower value will cause him to stay happy longer
	# the formula is (1 - (moodmodifier - batterylevel))
	moodmodifier = 4.05
	# END OF CONFIGURABLE VARIABLES
	#robot.world.connect_to_cubes()
	#robot.add_event_handler(cozmo.objects.EvtObjectAppeared, handle_object_appeared)
	#robot.add_event_handler(cozmo.objects.EvtObjectDisappeared, handle_object_disappeared)
	robot.world.image_annotator.add_annotator('camera_info', camera_info)
	camera = robot.camera
	camera.enable_auto_exposure()
	#camera.set_manual_exposure(67, camera.config.max_gain)
	freeplay = 0
	#robot.world.disconnect_from_cubes()
	robot.enable_all_reaction_triggers(False)
	robot.enable_stop_on_cliff(True)
	#os.system('cls' if os.name == 'nt' else 'clear')
	needslevel = 1
	lowbatcount = 0
	global cozmostate
	cozmostate = 0
	# some custom walls I have set up, it doesn't matter if you don't have them
	wall_obj1 = robot.world.define_custom_wall(CustomObjectTypes.CustomType02, CustomObjectMarkers.Circles2, 340, 120, 44, 44, True)
	wall_obj2 = robot.world.define_custom_wall(CustomObjectTypes.CustomType03, CustomObjectMarkers.Circles3, 120, 340, 44, 44, True)
	wall_obj3 = robot.world.define_custom_wall(CustomObjectTypes.CustomType04, CustomObjectMarkers.Circles4, 340, 120, 44, 44, True)
	wall_obj4 = robot.world.define_custom_wall(CustomObjectTypes.CustomType05, CustomObjectMarkers.Circles5, 340, 120, 44, 44, True)
	wall_obj5 = robot.world.define_custom_wall(CustomObjectTypes.CustomType06, CustomObjectMarkers.Hexagons2, 120, 340, 44, 44, True)
	homing = robot.world.define_custom_cube(CustomObjectTypes.CustomType07, CustomObjectMarkers.Diamonds2, 5, 44, 44, is_unique=True)
	wall_obj6=robot.world.define_custom_wall(CustomObjectTypes.CustomType08,CustomObjectMarkers.Hexagons3,120,340,44,44,True)
	wall_obj7=robot.world.define_custom_wall(CustomObjectTypes.CustomType09,CustomObjectMarkers.Triangles2,340,120,44,44,True)
	wall_obj8=robot.world.define_custom_wall(CustomObjectTypes.CustomType10,CustomObjectMarkers.Triangles3,340,120,44,44,True)
	#," battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2)
	# set up event monitoring
	q = None
	event_monitor.monitor(robot, q)
	freeplay = 0
	#
	# cozmostate controls the current state of the robot
	# 1 = charging
	# 2 = charged, on charger
	# 3 = freeplay
	# 4 = low battery but continuing play
	# 5 = low battery, finding charger
	while True:
		# charging?
		if (robot.is_on_charger == 1) and (robot.is_charging == 1):
			if cozmostate != 1:
				cozmostate=1
				program_updatestatusmessage("switching to charging state")
				robot_state_charging(cozmo.robot.Robot)
			elif cozmostate == 1:
				program_updatestatusmessage("charging")
				time.sleep(1)
		# charged?
		if (robot.is_on_charger == 1) and (robot.is_charging == 0):
			if cozmostate != 2:
				cozmostate=2
				program_updatestatusmessage("switching to charge complete state")
				time.sleep(1)
				#robot_state_freeplay(cozmo.robot.Robot)
			elif cozmostate == 2:
				program_updatestatusmessage("charge complete")
				time.sleep(1)
			#robot_state_charged()
		# freepokay
		if (robot.is_on_charger == 0) and (robot.battery_voltage >= 3.7):
			cozmostate=3
			program_updatestatusmessage("freeplay")
			time.sleep(1)
			#robot_state_freeplay()
		if (robot.is_on_charger == 0) and (robot.battery_voltage <= 3.7) and (batterycheckfail == 0):
			cozmostate=4
			program_updatestatusmessage("battery getting low but not critical")
			time.sleep(1)
		if (robot.is_on_charger == 0) and (robot.battery_voltage <= 3.7) and (batterycheckfail == 1):
			cozmostate=5
			program_updatestatusmessage("battery low, finding charger")
			time.sleep(1)
			#robot_action_findcharger()
		program_updatestatusmessage("main program loop complete")
		time.sleep(1)
			
# ROBOT STATES
#
def robot_state_charging(robot):
	global cozmostate, lowbatcount
	while (robot.is_on_charger == 1) and (robot.is_charging == 1):
		robot_action_needset(robot)
		#robot.world.disconnect_from_cubes()
		lowbatcount=0
		#os.system('cls' if os.name == 'nt' else 'clear')
		#print("State: charging, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
		# once in a while make random snoring noises
		program_updatestatusmessage("in charging loop")
		robot_status_snore_check()
		time.sleep(1)
			
def robot_state_charged(robot):
	global cozmostate
	if (robot.is_on_charger == 1) and (robot.is_charging == 0):
		lowbatcount=0
		cozmostate = 3   # go to freeplay
		cozmo_state_freeplay(cozmo.robot.Robot)
	time.sleep(1)

def robot_state_freeplay(robot):
	global cozmostate
	if freeplay==0 and cozmostate==freeplay:
		robot.drive_wheels(40, -40, l_wheel_acc=50, r_wheel_acc=50, duration=2)
		robot.play_anim_trigger(cozmo.anim.Triggers.OnSpeedtapGameCozmoWinHighIntensity, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=False).wait_for_completed()
		#os.system('cls' if os.name == 'nt' else 'clear')
		print("State: freeplay activating, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
		#robot.world.connect_to_cubes()
		robot.enable_all_reaction_triggers(True)
		robot.start_freeplay_behaviors()
		needslevel = 1 - (moodmodifier - robot.battery_voltage)
		freeplay=1
	robot_action_needset()
	
def robot_state_lowbattery(robot):
	global cozmostate
	time.sleep(1)
	
def robot_state_pickup(robot):
	time.sleep(1)
	
def robot_state_falling(robot):
	time.sleep(1)
	
def robot_state_stuckonside(robot):
	time.sleep(1)
	
# ROBOT ACTIONS 
#
def robot_action_docking(robot):
	global cozmostate
	time.sleep(1)

def robot_action_findcharger(robot):
	global cozmostate
	time.sleep(1)
	
def robot_action_needset(robot):
	global cozmostate
	needslevel = 1 - (moodmodifier - robot.battery_voltage)
	if needslevel < 0.1:
		needslevel = 0.1
	if needslevel > 1:
		needslevel = 1
	robot.set_needs_levels(repair_value=needslevel, energy_value=needslevel, play_value=needslevel)

def robot_action_cyclelights_red(robot):
	robot.set_all_backpack_lights(cozmo.lights.blue_light)
	time.sleep(5)
	robot.set_all_backpack_lights(cozmo.lights.off_light)

def robot_action_cyclelights_green(robot):
	robot.set_all_backpack_lights(cozmo.lights.blue_light)
	time.sleep(5)
	robot.set_all_backpack_lights(cozmo.lights.off_light)

def robot_action_cyclelights_blue(robot):
	robot.set_all_backpack_lights(cozmo.lights.blue_light)
	time.sleep(5)
	robot.set_all_backpack_lights(cozmo.lights.off_light)

def robot_action_backpack_color_cycler(backpackcolorint,robot):
	color1=cozmo.lights.Color(int_color=backpackcolorint, rgb=None, name=None)
	color2=cozmo.lights.Color(int_color=0, rgb=None, name=None)
	#define 3 lights and set different on/off and transition times
	light1=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=2000, off_period_ms=1000, transition_on_period_ms=1500, transition_off_period_ms=500)
	light2=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=1000, transition_on_period_ms=1000, transition_off_period_ms=2000)
	light3=cozmo.lights.Light(on_color=color1, off_color=color2, on_period_ms=1000, off_period_ms=2000, transition_on_period_ms=500, transition_off_period_ms=1500)
	#set the backpack lights
	robot.set_backpack_lights(None, light1, light2, light3, None)

# ROBOT STATUS CHECKS AND RESPONSES
#
def robot_status_schedule_check(robot: cozmo.robot.Robot):
	global cozmostate
	# day and time check - are we okay to play at this time and day?
	day_of_week = datetime.date.today().weekday() # 0 is Monday, 6 is Sunday
	ctime = datetime.datetime.now().time()
	playokay=0
	#it's weekend! Check for allowed times.
	if day_of_week > 4 and usescheduler == 1:
		if (ctime > datetime.time(weekendstartplay) and ctime < datetime.time(weekendstopplay)):
			playokay=1
	#it's a weekday! Check for allowed times.
	else:
		if (ctime > datetime.time(weekdaystartplay) and ctime < datetime.time(weekdaystopplay)) and usescheduler == 1:
			playokay=1
	# if the schedule says OK roll dice to see if we wake up
	if playokay==1:
		i = random.randint(1, 100)
		# wake up chance
		if i >= playchance:
			#os.system('cls' if os.name == 'nt' else 'clear')
			print("State: leaving charger, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
			#robot.world.connect_to_cubes()
			robot.set_all_backpack_lights(cozmo.lights.off_light)
			robot.play_anim("anim_gotosleep_getout_02").wait_for_completed()
			for _ in range(3):
				robot.drive_off_charger_contacts().wait_for_completed()
			time.sleep(2)
			robot.move_lift(-3)
			robot.drive_straight(distance_mm(50), speed_mmps(50)).wait_for_completed()
			robot.drive_straight(distance_mm(100), speed_mmps(50)).wait_for_completed()
	# we're out of schedule or didn't make the dice roll, back off and check again later.
	# if camera.exposure_ms < 66:
	# robot.say_text("light").wait_for_completed()
	# elif camera.exposure_ms >= 66:
	# robot.say_text("dark").wait_for_completed()
	x = 1
	while x < 20 and (robot.is_on_charger == 1):
		#os.system('cls' if os.name == 'nt' else 'clear')
		if playokay == 1:
			print("State: charged, schedule OK but not active, sleep loop %d of 30 before next check." % (x))
		else:
			print("State: charged,  not active by schedule, sleep loop %d of 30 before next check." % (x))
		robot_status_snore_check()
		if (robot.is_on_charger == 0):
			#os.system('cls' if os.name == 'nt' else 'clear')
			print("State: we were taken off the charger, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
			break
		time.sleep(5)
		robot.set_all_backpack_lights(cozmo.lights.off_light)
		x += 1
			
def robot_status_snore_check(robot: cozmo.robot.Robot):
	global cozmostate
	i = random.randint(1, 100)
	if i >= 98:
		robot.play_anim("anim_guarddog_fakeout_02").wait_for_completed()
		robot.play_anim("anim_gotosleep_sleeploop_01").wait_for_completed()
	elif i >= 85:
		robot.play_anim("anim_gotosleep_sleeploop_01").wait_for_completed()
	else:
		time.sleep(5)

def robot_status_battery_check(robot: cozmo.robot.Robot):
	global cozmostate
	if (robot.battery_voltage <= lowbatvoltage) and (robot.is_on_charger == 0):
		lowbatcount += 1
		time.sleep(1)
	if lowbatcount > 25 and (robot.is_on_charger == 0):
		cozmostate=lowbattery

def robot_status_random_reaction(robot: cozmo.robot.Robot):
	i = random.randint(1, 100)
	if i >= 90:
		robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabChatty, ignore_body_track=False, ignore_head_track=False, ignore_lift_track=False).wait_for_completed()
	else:
		time.sleep(0.5)
	robot.drive_wheels(-40, 40, l_wheel_acc=45, r_wheel_acc=45, duration=2)
	i = random.randint(1, 100)
	if i >= 90:
		robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabThinking, ignore_body_track=False, ignore_head_track=False, ignore_lift_track=False).wait_for_completed()
	else:
		time.sleep(0.5)
	robot.drive_wheels(-40, 40, l_wheel_acc=45, r_wheel_acc=45, duration=2)
	i = random.randint(1, 100)
	if i >= 90:
		robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabThinking, ignore_body_track=False, ignore_head_track=False, ignore_lift_track=False).wait_for_completed()
	else:
		time.sleep(0.5)

# FUTURE STATES NOT USED
#
def cubetap(robot: cozmo.robot.Robot):
	time.sleep(1)
	
def facecheck(robot: cozmo.robot.Robot):
	time.sleep(1)
	
# PROGRAM UPDATES
def program_updatestatusmessage(msg):
	robot = cozmo.robot.Robot
	#os.system('cls' if os.name == 'nt' else 'clear')
	print("State: %s" % msg)



cozmo.robot.Robot.drive_off_charger_on_connect = False
#cozmo.run_program(cozmo_unleashed, use_viewer=True)
# you may need to install a freeglut library, the cozmo SDK has documentation for this. If you don't have it comment the below line and uncomment the one above.
#cozmo.run_program(cozmo_unleashed, use_viewer=True, use_3d_viewer=True)
# which will give you remote control over Cozmo via WASD+QERF while the 3d window has focus
#
# below is just the program running without any camera view or 3d maps
cozmo.run_program(cozmo_unleashed)
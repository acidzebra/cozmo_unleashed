#!/usr/bin/env python3

# based on Copyright (c) 2016 Anki, Inc.
# modifications by acidzebra
#
# mod 1.0: 2017-10		
# -basic messy code		
# mod 1.1: 2018-02		
# - merged some stuff I had kicking around:		
# - scheduler (not easily configurable, have to look in the code, need to fix)		
# - set cozmo "needs" all to 1 so he won't be sulky when he plays		
# mod 1.2: 
# - code cleanup
# - added variables to start of program for scheduler, battery voltage
# - coupled battery levels to needs levels (cozmo's mood will go down as his battery levels go down)
# mod 1.2.1:
# - bugfixes
# - new bugs
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License in the file LICENSE.txt or at
#
#	 http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# 


#import required functions
# edit you may need to install some of these libraries
# specifically Pillow and numpy
#
#
import sys, os, datetime, random, time, math
import asyncio, cozmo, cozmo.objects, cozmo.util
import event_monitor
from cozmo.util import degrees, distance_mm, speed_mmps, Pose
from cozmo.objects import CustomObject, CustomObjectMarkers, CustomObjectTypes
from PIL import ImageDraw, ImageFont
import numpy as np

#define globals
global freeplay
freeplay=0

# image annotator for camera
# not really needed but I like to see what kind of gain/exposure compensation is going on in my environment
@cozmo.annotate.annotator
def camera_info(image, scale, annotator=None, world=None, **kw):
	d = ImageDraw.Draw(image)
	bounds = [3, 0, image.width, image.height]

	camera = world.robot.camera
	text_to_display = 'Exposure: %s ms\n' % camera.exposure_ms
	text_to_display += 'Gain: %.3f\n' % camera.gain
	text = cozmo.annotate.ImageText(text_to_display,position=cozmo.annotate.TOP_LEFT,line_spacing=2,color="white",outline_color="black", full_outline=True)
	text.render(d, bounds)

# def on_object_tapped(robot, evt=None, obj=None, tap_count=None, **kwargs):
		# print("you tapped a thing")
		# robot.play_anim_trigger(cozmo.anim.Triggers.HikingReactToEdge, ignore_body_track=True, ignore_head_track=True).wait_for_completed()

	
# main program and loops
def cozmo_unleashed(robot: cozmo.robot.Robot):

# CONFIGURABLE VARIABLES HERE
# CHANGE TO YOUR LIKING
	#
	# scheduler; allowed play times in 24H notation 
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
	playchance = 80
	#
	# low battery voltage - the point where Cozmo will start looking for his charger
	#
	lowbatvoltage = 3.7
	robot.set_robot_volume(0.2)
	# END OF CONFIGURABLE VARIABLES

	robot.world.connect_to_cubes()
	#robot.add_event_handler(cozmo.objects.EvtObjectAppeared, handle_object_appeared)
	#robot.add_event_handler(cozmo.objects.EvtObjectDisappeared, handle_object_disappeared)
	robot.world.image_annotator.add_annotator('camera_info', camera_info)
	camera = robot.camera
	camera.enable_auto_exposure()
	#camera.set_manual_exposure(67, camera.config.max_gain)
	global freeplay
	#robot.world.disconnect_from_cubes()
	robot.enable_all_reaction_triggers(False)
	robot.enable_stop_on_cliff(True)

	robot.set_needs_levels(repair_value=1, energy_value=1, play_value=1)
	#os.system('cls' if os.name == 'nt' else 'clear')
	needslevel = 1
	lowbatcount=0
	
	
	
	
	
	#robot.world.add_event_handler(cozmo.objects.EvtObjectTapped, on_object_tapped)
	
	
	
	
	#self.coz.world.add_event_handler(cozmo.objects.EvtObjectTapped, self.on_object_tapped)
	

	#
# custom object definitions
# I printed out the custom object markers and made a little playpen
# you can use this to somewhat control cozmo
# but if you don't have them it doesn't matter, the program will run just as well/badly
#
	wall_obj1 = robot.world.define_custom_wall(CustomObjectTypes.CustomType02, CustomObjectMarkers.Circles2, 340, 120, 44, 44, True)
	wall_obj2 = robot.world.define_custom_wall(CustomObjectTypes.CustomType03, CustomObjectMarkers.Circles3, 120, 340, 44, 44, True)
	wall_obj3 = robot.world.define_custom_wall(CustomObjectTypes.CustomType04, CustomObjectMarkers.Circles4, 340, 120, 44, 44, True)
	wall_obj4 = robot.world.define_custom_wall(CustomObjectTypes.CustomType05, CustomObjectMarkers.Circles5, 340, 120, 44, 44, True)
	wall_obj5 = robot.world.define_custom_wall(CustomObjectTypes.CustomType06, CustomObjectMarkers.Hexagons2, 120, 340, 44, 44, True)
	homing = robot.world.define_custom_cube(CustomObjectTypes.CustomType07, CustomObjectMarkers.Diamonds2, 5, 44, 44, is_unique=True)
	wall_obj6=robot.world.define_custom_wall(CustomObjectTypes.CustomType08,CustomObjectMarkers.Hexagons3,120,340,44,44,True)
	wall_obj7=robot.world.define_custom_wall(CustomObjectTypes.CustomType09,CustomObjectMarkers.Triangles2,340,120,44,44,True)
	wall_obj8=robot.world.define_custom_wall(CustomObjectTypes.CustomType10,CustomObjectMarkers.Triangles3,340,120,44,44,True)
	
	# set up event monitoring
	q = None
	event_monitor.monitor(robot, q)
# THIS IS WHERE THE STUFF REALLY HAPPENS
#

	while True:
#
#State 1: on charger, charging
#
		if (robot.is_on_charger == 1) and (robot.is_charging == 1):
			robot.set_needs_levels(repair_value=1, energy_value=1, play_value=1)
			#robot.world.disconnect_from_cubes()
			lowbatcount=0
			#os.system('cls' if os.name == 'nt' else 'clear')
			print("State: charging, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
			# once in a while make random snoring noises
			i = random.randint(1, 100)
			if i >= 98:
				robot.play_anim("anim_guarddog_fakeout_02").wait_for_completed()
				robot.play_anim("anim_gotosleep_sleeploop_01").wait_for_completed()
			elif i >= 80:
				robot.play_anim("anim_gotosleep_sleeploop_01").wait_for_completed()
			else:
				time.sleep(5)
			time.sleep(5)
			
			#TODO: figure out how to smoothly cycle lights
			robot.set_all_backpack_lights(cozmo.lights.blue_light)
			time.sleep(5)
			robot.set_all_backpack_lights(cozmo.lights.off_light)
#
#State 2: on charger, fully charged
#
		if (robot.is_on_charger == 1) and (robot.is_charging == 0):
			lowbatcount=0
			robot.set_needs_levels(repair_value=1, energy_value=1, play_value=1)
			# day and time check - are we okay to play at this time and day?
			day_of_week = datetime.date.today().weekday() # 0 is Monday, 6 is Sunday
			ctime = datetime.datetime.now().time()
			playokay=0
			#it's weekend! Check for allowed times.
			if day_of_week > 4:
				if (ctime > datetime.time(weekendstartplay) and ctime < datetime.time(weekendstopplay)):
					playokay=1
			#it's a weekday! Check for allowed times.
			else:
				if (ctime > datetime.time(weekdaystartplay) and ctime < datetime.time(weekdaystopplay)):
					playokay=1
			# if the schedule says OK roll dice to see if we wake up
			if playokay==1:
				i = random.randint(1, 100)
				# wake up chance
				if i >= playchance:
					#os.system('cls' if os.name == 'nt' else 'clear')
					print("State: leaving charger, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
					robot.world.connect_to_cubes()
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
				i = random.randint(1, 100)
				if i == 100:
					robot.play_anim("anim_guarddog_fakeout_02").wait_for_completed()
					robot.play_anim("anim_gotosleep_sleeploop_01").wait_for_completed()
				elif i >= 80:
					robot.play_anim("anim_gotosleep_sleeploop_01").wait_for_completed()
				else:
					time.sleep(5)
					#robot.play_anim("anim_gotosleep_off_01").wait_for_completed()
				if (robot.is_on_charger == 0):
					#os.system('cls' if os.name == 'nt' else 'clear')
					print("State: we were taken off the charger, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
					break
				time.sleep(5)
				robot.set_all_backpack_lights(cozmo.lights.off_light)
				x += 1
#
#State 3: not on charger, low battery
#

		# basic 'trigger guard' so Cozmo doesn't go to charger immediately if the voltage happens to dip below 3.7
		if (robot.battery_voltage <= lowbatvoltage) and (robot.is_on_charger == 0):
			lowbatcount += 1
			time.sleep(1)
		
		if lowbatcount > 3 and (robot.is_on_charger == 0):
			#back off from whatever we were doing
			if freeplay==1:
				robot.abort_all_actions(log_abort_messages=False)
				robot.wait_for_all_actions_completed()
				robot.stop_freeplay_behaviors()
				robot.enable_all_reaction_triggers(False)	
				#robot.world.disconnect_from_cubes()
				freeplay=0
				robot.play_anim_trigger(cozmo.anim.Triggers.NeedsMildLowEnergyRequest, ignore_body_track=True).wait_for_completed()
				robot.set_head_angle(degrees(0)).wait_for_completed()
				robot.move_lift(-3)
				robot.drive_straight(distance_mm(-30), speed_mmps(50)).wait_for_completed()
			robot.set_all_backpack_lights(cozmo.lights.blue_light)
			needslevel = 1 - (4.2 - robot.battery_voltage)
			if needslevel < 0.1:
				needslevel = 0.1
			if needslevel > 1:
				needslevel = 1
			robot.set_needs_levels(repair_value=needslevel, energy_value=needslevel, play_value=needslevel)
			#os.system('cls' if os.name == 'nt' else 'clear')
			print("State: finding charger, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
			# charger location search
			charger = None
			# see if we already know where the charger is
			if robot.world.charger:
				if robot.world.charger.pose.origin_id == robot.pose.origin_id:
					#we know where the charger is
					#os.system('cls' if os.name == 'nt' else 'clear')
					print("State: charger position known, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
					robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabSurprise, ignore_body_track=True, ignore_head_track=True).wait_for_completed()
					robot.move_lift(-3)
					robot.set_head_angle(degrees(0)).wait_for_completed()
					time.sleep(1)
					charger = robot.world.charger
					action = robot.go_to_pose(charger.pose)
					action.wait_for_completed()
					# get a little distance and have a look
					robot.drive_straight(distance_mm(-50), speed_mmps(50)).wait_for_completed()
					robot.play_anim_trigger(cozmo.anim.Triggers.HikingReactToEdge, ignore_body_track=True, ignore_head_track=True).wait_for_completed()
# here is a charger location finder but it should be broken out into its own section	
# I should modify if lowbatcount > 5 and (robot.battery_voltage <= lowbatvoltage) and (robot.is_on_charger == 0):
# to include a check for knowing where the charger is		
			else:
				#os.system('cls' if os.name == 'nt' else 'clear')
				print("State: looking for charger, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
				robot.play_anim_trigger(cozmo.anim.Triggers.SparkIdle, ignore_body_track=True).wait_for_completed()
				robot.move_lift(-3)
				robot.set_head_angle(degrees(0)).wait_for_completed()
				robot.drive_straight(distance_mm(-20), speed_mmps(50)).wait_for_completed()
				# randomly drive around for a bit and see if we can spot the charger
				#TODO: better search AI and beter code
				loops=3
				while loops>0:
					if robot.world.charger:
						loops=0
						charger = robot.world.charger
						#os.system('cls' if os.name == 'nt' else 'clear')
						robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabSurprise, ignore_body_track=True, ignore_head_track=True).wait_for_completed()
						print("State: breaking charger loop as charger is known, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
						break
					needslevel = 1 - (4.2 - robot.battery_voltage)
					if needslevel < 0.1:
						needslevel = 0.1
					if needslevel > 1:
						needslevel = 1
					robot.set_needs_levels(repair_value=needslevel, energy_value=needslevel, play_value=needslevel)
					x= random.randrange(-100, 101, 200)
					y= random.randrange(-100, 101, 200)
					#os.system('cls' if os.name == 'nt' else 'clear')
					print("State: looking for charger, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
					robot.go_to_pose(Pose(x, y, 0, angle_z=degrees(0)), relative_to_robot=True).wait_for_completed()
					robot.drive_wheels(40, -40, l_wheel_acc=50, r_wheel_acc=50, duration=2)
					time.sleep(0.5)
					robot.drive_wheels(-40, 40, l_wheel_acc=45, r_wheel_acc=45, duration=2)
					time.sleep(0.7)
					robot.drive_wheels(-40, 40, l_wheel_acc=45, r_wheel_acc=45, duration=2)
					time.sleep(0.5)
					robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabThinking, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=True).wait_for_completed()
					if robot.world.charger:
						loops=0
						#os.system('cls' if os.name == 'nt' else 'clear')
						charger = robot.world.charger
						print("State: breaking charger loop as charger is known, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
						robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabSurprise, ignore_body_track=True, ignore_head_track=True).wait_for_completed()
						break
					time.sleep(0.5)
					#robot.play_anim_trigger(cozmo.anim.Triggers.HikingInterestingEdgeThought, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=True).wait_for_completed()
					loops=loops-1
				#os.system('cls' if os.name == 'nt' else 'clear')
				print("State: locator loop complete. battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
				time.sleep(1)
			

#			
# Charger location and docking handling here
#
#TODO: improve this spaghetti code
			if charger and robot.world.charger:
				while (robot.is_on_charger == 0):
					robot.set_lift_height(0.8,0.8,0.8,0.1).wait_for_completed()
					# drive near to the charger, and then stop.
					#os.system('cls' if os.name == 'nt' else 'clear')
					print("State: moving to charger, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
					robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabChatty, ignore_body_track=True, ignore_head_track=True).wait_for_completed()
					robot.move_lift(-3)
					robot.set_head_angle(degrees(0)).wait_for_completed()
					charger = robot.world.charger
					action = robot.go_to_pose(charger.pose)
					action.wait_for_completed()
					# get a little distance and have a look
					robot.drive_straight(distance_mm(-50), speed_mmps(50)).wait_for_completed()
					robot.set_head_light(False)
					# we should be right in front of the charger, can we see it?
					if not charger:
						# we can't see it. Remove charger from navigation map and quit this loop.
						robot.world.charger = None
						charger = None
						robot.play_anim_trigger(cozmo.anim.Triggers.ReactToPokeReaction, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=True).wait_for_completed()
						#os.system('cls' if os.name == 'nt' else 'clear')
						print("State: charger not found, clearing map. battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
						break
					# okay it's there, attempt to dock.
					action = robot.go_to_pose(charger.pose)
					action.wait_for_completed()
					robot.drive_straight(distance_mm(-20), speed_mmps(50)).wait_for_completed()
					i = random.randint(1, 100)
					if i >= 85:
						robot.play_anim_trigger(cozmo.anim.Triggers.FeedingReactToShake_Normal, ignore_body_track=True, ignore_head_track=True).wait_for_completed()
					#os.system('cls' if os.name == 'nt' else 'clear')
					print("State: docking, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
					robot.turn_in_place(degrees(95)).wait_for_completed()
					robot.turn_in_place(degrees(95)).wait_for_completed()
					time.sleep( 1 )
					robot.play_anim_trigger(cozmo.anim.Triggers.CubePounceFake, ignore_body_track=True).wait_for_completed()
					robot.set_head_angle(degrees(0)).wait_for_completed()
					robot.drive_straight(distance_mm(-145), speed_mmps(150)).wait_for_completed()
					time.sleep( 1 )
					# check if we're now docked
					if robot.is_on_charger:
						# Yes! we're docked!
						robot.set_needs_levels(repair_value=1, energy_value=1, play_value=1)
						robot.play_anim("anim_sparking_success_02").wait_for_completed()
						robot.set_head_angle(degrees(0)).wait_for_completed()
						#os.system('cls' if os.name == 'nt' else 'clear')
						print("State: docked, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
						robot.set_all_backpack_lights(cozmo.lights.off_light)
						robot.play_anim("anim_gotosleep_getin_01").wait_for_completed()
						robot.play_anim("anim_gotosleep_sleeping_01").wait_for_completed()
					# No, we missed. Back off and try again
					else:
						#os.system('cls' if os.name == 'nt' else 'clear')
						print("State: failed to dock with charger, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
						charger = None
						robot.play_anim_trigger(cozmo.anim.Triggers.AskToBeRightedRight, ignore_body_track=True).wait_for_completed()
						robot.move_lift(-3)
						robot.set_head_angle(degrees(0)).wait_for_completed()
						#os.system('cls' if os.name == 'nt' else 'clear')
						print("State: backing off to attempt docking, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
						robot.drive_straight(distance_mm(50), speed_mmps(50)).wait_for_completed()
						robot.turn_in_place(degrees(-3)).wait_for_completed()
						robot.drive_straight(distance_mm(150), speed_mmps(50)).wait_for_completed()
						robot.turn_in_place(degrees(95)).wait_for_completed()
						robot.turn_in_place(degrees(96)).wait_for_completed()
						robot.set_head_angle(degrees(0)).wait_for_completed()
						if not robot.world.charger:
						# #No we can't see it. Remove charger from navigation map and quit this loop.
							robot.world.charger = None
							charger = None
							robot.play_anim_trigger(cozmo.anim.Triggers.ReactToPokeReaction, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=True).wait_for_completed()
							#os.system('cls' if os.name == 'nt' else 'clear')
							print("State: charger not found, clearing map. battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
							break
						time.sleep( 1 )
			else:
			# we have not managed to find the charger. Falling back to freeplay with occasional checks
				#robot.world.charger = None
				robot.play_anim_trigger(cozmo.anim.Triggers.MemoryMatchPlayerWinGame, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=False).wait_for_completed()
				#robot.world.connect_to_cubes()
				robot.enable_all_reaction_triggers(True)
				robot.start_freeplay_behaviors()
				freeplay=1
				x=0
				while x<20:
					if not robot.world.charger:
						time.sleep( 5 )
						if robot.world.charger:
							x=20
							charger = robot.world.charger
							#os.system('cls' if os.name == 'nt' else 'clear')
							print("State: breaking freeplay loop as charger is known, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
							break
						#os.system('cls' if os.name == 'nt' else 'clear')
						print("State: charger not found, falling back to freeplay for a bit, loop %d of 20." % x)
					x+=1
					if robot.world.charger:
						print("State: charger is known, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
						charger = robot.world.charger
					break
				#after 100 seconds or spotting the charger end freeplay
				robot.enable_all_reaction_triggers(False)
				robot.stop_freeplay_behaviors()
				freeplay=0
			#os.system('cls' if os.name == 'nt' else 'clear')
			print("State: charger program loop complete, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
			time.sleep(1)


#			
#State 4: not on charger, good battery
#
		if (robot.battery_voltage > lowbatvoltage) and (robot.is_on_charger == 0):
			#lowbatcount == 0
			#initiate freeplay
			if freeplay==0:
				robot.drive_wheels(40, -40, l_wheel_acc=50, r_wheel_acc=50, duration=2)
				robot.play_anim_trigger(cozmo.anim.Triggers.OnSpeedtapGameCozmoWinHighIntensity, ignore_body_track=True, ignore_head_track=True, ignore_lift_track=False).wait_for_completed()
				#os.system('cls' if os.name == 'nt' else 'clear')
				print("State: freeplay activating, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
				#robot.world.connect_to_cubes()
				robot.enable_all_reaction_triggers(True)
				robot.start_freeplay_behaviors()
				needslevel = 1 - (4.2 - robot.battery_voltage)
				#clamp values
				if needslevel < 0.1:
					needslevel = 0.1
				if needslevel > 1:
					needslevel = 1
				robot.set_needs_levels(repair_value=needslevel, energy_value=needslevel, play_value=needslevel)
				freeplay=1
			#os.system('cls' if os.name == 'nt' else 'clear')
			print("State: freeplay, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
			needslevel = 1 - (4.2 - robot.battery_voltage)
			#clamp values
			if needslevel < 0.1:
				needslevel = 0.1
			if needslevel > 1:
				needslevel = 1
			robot.set_needs_levels(repair_value=needslevel, energy_value=needslevel, play_value=needslevel)
			time.sleep(2)
			# if camera.exposure_ms < 66:
				# print("light")
			# elif camera.exposure_ms >= 66:
				# print("dark")
		
		#os.system('cls' if os.name == 'nt' else 'clear')
		needslevel = 1 - (4.2 - robot.battery_voltage)
		if needslevel < 0.1:
			needslevel = 0.1
		if needslevel > 1:
			needslevel = 1
		robot.set_needs_levels(repair_value=needslevel, energy_value=needslevel, play_value=needslevel)
		i = random.randint(1, 100)
		if i >= 98:
			robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabChatty, ignore_body_track=True, ignore_head_track=True).wait_for_completed()
		print("State: freeplay state program loop complete, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
		time.sleep(2)
	#os.system('cls' if os.name == 'nt' else 'clear')

#
# end of loop
	needslevel = 1 - (4.2 - robot.battery_voltage)
	if needslevel < 0.1:
		needslevel = 0.1
	if needslevel > 1:
		needslevel = 1
	robot.set_needs_levels(repair_value=needslevel, energy_value=needslevel, play_value=needslevel)
	i = random.randint(1, 100)
	if i >= 90:
		robot.play_anim_trigger(cozmo.anim.Triggers.CodeLabChatty, ignore_body_track=True, ignore_head_track=True).wait_for_completed()
	time.sleep(1)
	print("State: main program loop complete, battery %s" % str(round(robot.battery_voltage, 2))," energy %s" % round(needslevel, 2))
	time.sleep( 3 )

	
cozmo.robot.Robot.drive_off_charger_on_connect = False
#cozmo.run_program(cozmo_unleashed, use_viewer=True)
# you may need to install a freeglut library, the cozmo SDK has documentation for this. If you don't have it comment the below line and uncomment the one above.
cozmo.run_program(cozmo_unleashed, use_viewer=True, use_3d_viewer=True)
# which will give you remote control over Cozmo via WASD+QERF while the 3d window has focus
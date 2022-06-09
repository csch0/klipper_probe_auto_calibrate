# Support for led strips
#
# Copyright (C) 2022  Christoph Schoening <schoning.christoph@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.
import logging

from mcu import MCU_endstop


class ProbeZCalibrate:
    def __init__(self, config):
        self.config = config
        self.printer = config.get_printer()

        self.nozzle_pos = self._get_position("nozzle_xy_position")
        self.switch_pos = self._get_position("switch_xy_position")
        self.switch_offset = config.getfloat('switch_offset', 0.0, above=0.)

        self.samples = config.getint('samples',
                                     None, minval=1)
        self.samples_tolerance = config.getfloat('samples_tolerance',
                                                 None, above=0.)
        self.samples_tolerance_retries = config.getint('samples_tolerance_retries',
                                                       None, minval=0)
        atypes = {'none': None, 'median': 'median', 'average': 'average'}
        self.samples_result = config.getchoice('samples_result',
                                               atypes, 'none')

        self.probing_speed = config.getfloat('probing_speed',
                                             None, above=0.)
        self.second_probing_speed = config.getfloat('second_probing_speed',
                                                    None, above=0.)
        self.probing_retract_dist = config.getfloat('probing_retract_dist',
                                                    None, above=0.)

        self.clearance = config.getfloat('clearance', 20, above=5)
        self.position_min = config.getfloat('position_min', None)

        self.speed = config.getfloat('speed', 50.0, above=0.)
        self.lift_speed = config.getfloat('lift_speed', None, above=0.)

        gcode_macro = self.printer.load_object(config, 'gcode_macro')
        self.start_gcode = gcode_macro.load_template(config, 'start_gcode', '')
        self.end_gcode = gcode_macro.load_template(config, 'end_gcode', '')

        pin = config.get('pin')
        pins = self.printer.lookup_object('pins')

        self.mcu_endstop = pins.setup_pin('endstop', pin)

        # pin_params = pins.lookup_pin(pin, can_invert=True, can_pullup=True)
        # mcu = pin_params['chip']
        # self.mcu_endstop = mcu.setup_pin('endstop', pin_params)

        self.add_stepper = self.mcu_endstop.add_stepper

        self.gcode = self.printer.lookup_object('gcode')
        self.gcode.register_command(
            'PROBE_Z_CALIBRATE', self.cmd_PROBE_Z_CALIBRATE, desc="aaa")

        self.printer.register_event_handler('klippy:connect',
                                            self._handle_connect)

        self.printer.register_event_handler('klippy:mcu_identify',
                                            self._handle_mcu_identify)

        self.printer.register_event_handler("homing:home_rails_end",
                                            self.handle_home_rails_end)

    def _handle_connect(self):
        probe = self.printer.lookup_object('probe', default=None)
        if probe is None:
            raise self.printer.config_error(
                "A probe is needed for %s" % (self.config.get_name()))

        # use the values of the probe as default fallback
        if self.samples is None:
            self.samples = probe.sample_count
        if self.samples_tolerance is None:
            self.samples_tolerance = probe.samples_tolerance
        if self.samples_tolerance_retries is None:
            self.samples_tolerance_retries = probe.samples_retries
        if self.samples_result is None:
            self.samples_result = probe.samples_result

        if self.lift_speed is None:
            self.lift_speed = probe.lift_speed

    def _handle_mcu_identify(self):
        toolhead = self.printer.lookup_object('toolhead')
        for stepper in toolhead.get_kinematics().get_steppers():
            if stepper.is_active_axis('z'):
                self.add_stepper(stepper)

    def handle_home_rails_end(self, homing_state, rails):
        for rail in rails:
            if rail.get_steppers()[0].is_active_axis('z'):
                # use the values as the z axis as default fallback
                if self.probing_speed is None:
                    self.probing_speed = rail.homing_speed
                if self.second_probing_speed is None:
                    self.second_probing_speed = rail.second_homing_speed
                if self.probing_retract_dist is None:
                    self.probing_retract_dist = rail.homing_retract_dist
                if self.position_min is None:
                    self.position_min = rail.position_min

    def _calc_mean(self, values):
        return sum(values) / len(values)

    def _calc_median(self, values):
        sorted_values = sorted(values)
        middle = len(values) // 2
        if (len(values) & 1) == 1:
            # odd number of samples
            return sorted_values[middle]
        # even number of samples
        return self._calc_mean(sorted_values[middle-1:middle+1])

    def _get_position(self, name):
        try:
            position = self.config.get(name)
            x_pos, y_pos = position.split(',')
            return [float(x_pos), float(y_pos), None]
        except:
            raise self.config.error("Unable to parse %s in %s"
                                    % (name, self.config.get_name()))

    def _probe(self):
        toolhead = self.printer.lookup_object('toolhead')

        # set position_min
        probing_pos = toolhead.get_position()
        probing_pos[2] = self.position_min

        homing = self.printer.lookup_object('homing')
        current_pos = homing.probing_move(
            self.mcu_endstop, probing_pos, self.probing_speed)

        # retract
        self._move([None, None, current_pos[2] + self.probing_retract_dist],
                   self.lift_speed)

        self.gcode.respond_info("probe at %.3f,%.3f is z=%.6f"
                                % (current_pos[0], current_pos[1], current_pos[2]))

        return current_pos[2]

    def _probe_on_endstop(self, position):
        toolhead = self.printer.lookup_object('toolhead')

        current_pos = toolhead.get_position()
        if current_pos[2] < self.clearance:
            self._move([None, None, self.clearance], self.lift_speed)

        # move to probing location
        self._move(list(position), self.speed)

        # probe at location
        retries = 0
        z_positions = []
        while len(z_positions) < self.samples:
            z_position = self._probe()
            z_positions += [z_position]
            if max(z_positions) - min(z_positions) > self.samples_tolerance:
                if retries >= self.helper.retries:
                    raise self.gcmd.error("Probe samples exceed tolerance")
                self.gcmd.respond_info("Probe samples exceed tolerance."
                                       " Retrying...")
                retries += 1
                z_positions = []

        if self.samples_result == 'median':
            return self._calc_median(z_positions)
        return self._calc_mean(z_positions)

    def _move(self, coordinate, speed):
        toolhead = self.printer.lookup_object('toolhead')
        toolhead.manual_move(coordinate, speed)

    def cmd_PROBE_Z_CALIBRATE(self, gcmd):

        self.start_gcode.run_gcode_from_command()

        # probe the nozzle
        nozzle_zero = self._probe_on_endstop(self.nozzle_pos)
        # probe the switch
        switch_zero = self._probe_on_endstop(self.switch_pos)

        z_offset = (switch_zero - nozzle_zero + self.switch_offset)

        # print result
        self.gcode.respond_info("PROBE_Z_CALIBRATE: NOZZLE=%.3f"
                                " SWITCH=%.3f --> Z_OFFSET=%.6f"
                                % (nozzle_zero, switch_zero, z_offset))

        self.end_gcode.run_gcode_from_command()

        self.gcode.respond_info(
            "%s: z_offset: %.3f\n"
            "The SAVE_CONFIG command will update the printer config file\n"
            "with the above and restart the printer." % ("probe", z_offset))
        configfile = self.printer.lookup_object('configfile')
        configfile.set("probe", 'z_offset', "%.6f" % (z_offset))


def load_config(config):
    return ProbeZCalibrate(config)

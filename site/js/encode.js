/* One decision, written the way each driver writes it.

   This is the only part of the page that speaks a protocol, and it is the part most likely to drift
   quietly away from the Python it imitates — a register renamed, a unit forgotten. So it is checked
   the same way the controller is: `site/test/twin.test.mjs` takes the frames that
   `scripts/wire.py` recorded off a real socket and asserts that these functions reproduce them, byte
   for byte for Modbus and field for field for OCPP. If they ever disagree, the build fails. */
(function () {
  'use strict';

  var OFFER_DA = 2000; // holding register: what to offer the car, in tenths of an amp
  var WRITE_MULTIPLE = 0x10;
  var MIN_CHARGE_A = 6.0;

  function byte(value) {
    return ('0' + (value & 0xff).toString(16)).slice(-2);
  }

  function word(value) {
    return byte(value >> 8) + byte(value);
  }

  window.Wire = {
    OFFER_DA: OFFER_DA,

    /* The frame a Modbus TCP wallbox is given: an MBAP header, then write two registers — the
       current in tenths of an amp, and how many phases to use. */
    modbusWrite: function (amps, phases, transaction, unit) {
      var pdu =
        byte(WRITE_MULTIPLE) + word(OFFER_DA) + word(2) + byte(4) + word(Math.round(amps * 10)) + word(phases);
      var mbap = word(transaction || 0) + word(0) + word(pdu.length / 2 + 1) + byte(unit === undefined ? 1 : unit);
      return mbap + pdu;
    },

    /* The message an OCPP 1.6J charge point is sent. A limit below the floor is sent as zero:
       "charge at four amps" is not a thing that exists, and the station would have to invent a
       meaning for it. */
    ocppProfile: function (amps, phases, id) {
      var limit = amps >= MIN_CHARGE_A ? amps : 0.0;
      return [
        2,
        String(id),
        'SetChargingProfile',
        {
          connectorId: 1,
          csChargingProfiles: {
            chargingProfileId: 1,
            stackLevel: 0,
            chargingProfilePurpose: 'TxDefaultProfile',
            chargingProfileKind: 'Absolute',
            chargingSchedule: {
              chargingRateUnit: 'A',
              chargingSchedulePeriod: [{ startPeriod: 0, limit: limit, numberPhases: phases }],
            },
          },
        },
      ];
    },
  };
})();

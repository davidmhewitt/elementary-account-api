window.onload = function(e){
    var cardButton = document.getElementById('card-button');
    var clientSecret = cardButton.dataset.secret;
    var account_id = cardButton.dataset.account;

    var stripe = Stripe('pk_test_MrafeP8AsKSMKCZFfHmp6Upc');

    var cardButton = document.getElementById('card-button');
    var clientSecret = cardButton.dataset.secret;
    var elements = stripe.elements();

    var form_container = document.querySelector('.form-container');

    var form = form_container.querySelector('form');
    var error = form.querySelector('.error');
    var errorMessage = error.querySelector('.message');

    var card = elements.create('card', {
        iconStyle: 'solid',
        style: {
          base: {
            iconColor: '#abacae',
            color: '#333',
            fontFamily: 'Open Sans, Segoe UI, sans-serif',
            fontSize: '12px',
            fontSmoothing: 'antialiased',

            ':-webkit-autofill': {
              color: '#fce883',
            },
            '::placeholder': {
              color: '#abacae',
            },
          },
          invalid: {
            iconColor: '#c6262e',
            color: '#c6262e',
          },
        },
    });

    card.mount('#card-mount');
    // Listen for errors from each Element, and show error messages in the UI.
    card.on('change', function(event) {
      if (event.error) {
        error.classList.add('visible');
        errorMessage.innerText = event.error.message;
      } else {
        error.classList.remove('visible');
      }
    });

    card.on('ready', function(event) {
      form_container.classList.remove('submitting');
    });

    function enableInputs() {
      Array.prototype.forEach.call(
        form.querySelectorAll(
          "input[type='text'], input[type='email'], input[type='tel']"
        ),
        function(input) {
          input.removeAttribute('disabled');
        }
      );
    }

    function disableInputs() {
      Array.prototype.forEach.call(
        form.querySelectorAll(
          "input[type='text'], input[type='email'], input[type='tel']"
        ),
        function(input) {
          input.setAttribute('disabled', 'true');
        }
      );
    }

    function triggerBrowserValidation() {
      // The only way to trigger HTML5 form validation UI is to fake a user submit
      // event.
      var submit = document.createElement('input');
      submit.type = 'submit';
      submit.style.display = 'none';
      form.appendChild(submit);
      submit.click();
      submit.remove();
    }

    // Listen on the form's 'submit' handler...
    form.addEventListener('submit', function(e) {
      e.preventDefault();

      // Trigger HTML5 validation UI on the form if any of the inputs fail
      // validation.
      var plainInputsValid = true;
      Array.prototype.forEach.call(form.querySelectorAll('input'), function(
        input
      ) {
        if (input.checkValidity && !input.checkValidity()) {
          plainInputsValid = false;
          return;
        }
      });
      if (!plainInputsValid) {
        triggerBrowserValidation();
        return;
      }

      // Show a loading screen...
      form_container.classList.add('submitting');

      // Disable all inputs.
      disableInputs();

      // Gather additional customer data we may have collected in our form.
      var name = form.querySelector('#field-name');

      stripe.confirmCardSetup(
        clientSecret,
        {
          payment_method: {
            card: card,
            billing_details: {
              name: name.value,
            },
          },
        }
      ).then(function(result) {
        // Stop loading!
        form_container.classList.remove('submitting');

        if (result.setupIntent) {
          form_container.classList.add('submitted');
          setTimeout(function () {
              window.location.href = '/api/v1/success/1'
          }, 1000);
        } else {
          error.classList.add('visible');
          errorMessage.innerText = result.error.message;
          // Otherwise, un-disable inputs.
          enableInputs();
        }
      });
    });
}

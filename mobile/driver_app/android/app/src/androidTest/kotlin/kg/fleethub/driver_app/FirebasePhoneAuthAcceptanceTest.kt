package kg.fleethub.driver_app

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.google.android.gms.tasks.Tasks
import com.google.firebase.FirebaseException
import com.google.firebase.auth.*
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Opt-in real Firebase test; runner arguments must be fictional Console test credentials. */
@RunWith(AndroidJUnit4::class)
class FirebasePhoneAuthAcceptanceTest {
    @Test fun consoleTestPhoneSignsIn() {
        val args = InstrumentationRegistry.getArguments()
        val phone = args.getString("testPhoneNumber")
        val code = args.getString("testSmsCode")
        assumeTrue("Console test credentials required", !phone.isNullOrBlank() && !code.isNullOrBlank())
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        val context = instrumentation.targetContext
        val activity = instrumentation.startActivitySync(context.packageManager.getLaunchIntentForPackage(context.packageName)!!)
        val auth = FirebaseAuth.getInstance()
        val done = CountDownLatch(1)
        var credential: PhoneAuthCredential? = null
        var failure: FirebaseException? = null
        try {
            instrumentation.runOnMainSync {
                val options = PhoneAuthOptions.newBuilder(auth).setPhoneNumber(phone!!)
                    .setTimeout(60L, TimeUnit.SECONDS).setActivity(activity)
                    .setCallbacks(object: PhoneAuthProvider.OnVerificationStateChangedCallbacks() {
                        override fun onVerificationCompleted(value: PhoneAuthCredential) { credential=value;done.countDown() }
                        override fun onVerificationFailed(error: FirebaseException) { failure=error;done.countDown() }
                        override fun onCodeSent(id: String, token: PhoneAuthProvider.ForceResendingToken) {
                            credential=PhoneAuthProvider.getCredential(id,code!!);done.countDown()
                        }
                    }).build()
                PhoneAuthProvider.verifyPhoneNumber(options)
            }
            assertTrue("Firebase verification callback timed out", done.await(90,TimeUnit.SECONDS))
            if(failure != null) fail("Firebase verification stage: ${(failure as? FirebaseAuthException)?.errorCode ?: failure!!.javaClass.simpleName}")
            val user=Tasks.await(auth.signInWithCredential(credential!!),60,TimeUnit.SECONDS).user
            assertNotNull(user)
            assertFalse(Tasks.await(user!!.getIdToken(false),60,TimeUnit.SECONDS).token.isNullOrEmpty())
        } finally { auth.signOut() }
    }
}

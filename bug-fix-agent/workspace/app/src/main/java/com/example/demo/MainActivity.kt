package com.example.demo

class User(
    val name: String
)

class MainActivity {

    fun onCreate() {

        val user: User? = null

        // BUG: Force unwrap causes NullPointerException
        println(user?.name)
    }
}
